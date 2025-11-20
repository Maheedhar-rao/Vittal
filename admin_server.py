from flask import Flask, jsonify, request
import os

app = Flask(__name__)

@app.route('/')
def admin():
    with open('admin.html', 'r') as f:
        html = f.read()
    
    html = html.replace("'YOUR_SUPABASE_URL'", f"'{os.environ.get('SUPABASE_URL', '')}'")
    html = html.replace("'YOUR_SUPABASE_ANON_KEY'", f"'{os.environ.get('SUPABASE_ANON_KEY', '')}'")
    
    return html

@app.route('/check-pdfs', methods=['POST'])
def check_pdfs():
    if 'files' not in request.files:
        return jsonify({"error": "No files uploaded"}), 400
    
    from pikepdf import Pdf
    
    files = request.files.getlist('files')
    results = []
    
    for file in files:
        result = {
            "filename": file.filename,
            "corrupted": False,
            "successful_layers": 0,
            "layers": [],
            "errors": [],
            "pdf_valid": False
        }
        
        try:
            # Save temporarily
            temp_path = f"/tmp/{file.filename}"
            file.save(temp_path)
            
            # Validate 6 layers
            pdf = Pdf.open(temp_path)
            result["pdf_valid"] = True
            
            # Layer 1: Info Dictionary
            try:
                docinfo = pdf.docinfo
                has_fingerprint = "/FingerprintID" in docinfo or any(
                    k for k in docinfo.keys() if "fingerprint" in str(k).lower()
                )
                has_recipient = "/Recipient" in docinfo or "/WatermarkOwner" in docinfo or any(
                    k for k in docinfo.keys() if "recipient" in str(k).lower() or "owner" in str(k).lower()
                )
                
                if has_fingerprint or has_recipient or len(docinfo) > 0:
                    result["layers"].append({"layer": 1, "status": "OK"})
                    result["successful_layers"] += 1
                else:
                    result["layers"].append({"layer": 1, "status": "FAIL"})
                    result["errors"].append({"layer": 1, "error": "Info dictionary missing"})
                    result["corrupted"] = True
            except Exception as e:
                result["layers"].append({"layer": 1, "status": "FAIL"})
                result["errors"].append({"layer": 1, "error": str(e)})
                result["corrupted"] = True
            
            # Layer 2: XMP Metadata
            try:
                has_xmp = hasattr(pdf.Root, "Metadata") and pdf.Root.Metadata is not None
                if has_xmp:
                    result["layers"].append({"layer": 2, "status": "OK"})
                    result["successful_layers"] += 1
                else:
                    result["layers"].append({"layer": 2, "status": "FAIL"})
                    result["errors"].append({"layer": 2, "error": "XMP metadata missing"})
                    result["corrupted"] = True
            except Exception as e:
                result["layers"].append({"layer": 2, "status": "FAIL"})
                result["errors"].append({"layer": 2, "error": str(e)})
                result["corrupted"] = True
            
            # Layer 3: Custom Properties (dealid, fingerprint, recipient, timestamp)
            try:
                docinfo = pdf.docinfo
                custom_keys = [k for k in docinfo.keys() if any(
                    prop in str(k).lower() for prop in ["dealid", "fingerprint", "recipient", "timestamp"]
                )]
                
                if custom_keys:
                    result["layers"].append({"layer": 3, "status": "OK"})
                    result["successful_layers"] += 1
                else:
                    result["layers"].append({"layer": 3, "status": "FAIL"})
                    result["errors"].append({"layer": 3, "error": "Custom properties missing (need: dealid/fingerprint/recipient/timestamp)"})
                    result["corrupted"] = True
            except Exception as e:
                result["layers"].append({"layer": 3, "status": "FAIL"})
                result["errors"].append({"layer": 3, "error": str(e)})
                result["corrupted"] = True
            
            # Layer 4: Trailer ID
            try:
                has_trailer_id = hasattr(pdf, "trailer") and "/ID" in pdf.trailer
                if has_trailer_id:
                    result["layers"].append({"layer": 4, "status": "OK"})
                    result["successful_layers"] += 1
                else:
                    result["layers"].append({"layer": 4, "status": "FAIL"})
                    result["errors"].append({"layer": 4, "error": "Trailer ID missing"})
                    result["corrupted"] = True
            except Exception as e:
                result["layers"].append({"layer": 4, "status": "FAIL"})
                result["errors"].append({"layer": 4, "error": str(e)})
                result["corrupted"] = True
            
            # Layer 5: First Page Annotations (optional if no tracking URL)
            try:
                first_page = pdf.pages[0]
                has_annotations = False
                
                if "/Annots" in first_page and len(first_page.Annots) > 0:
                    # Check if annotations have required properties
                    for annot in first_page.Annots:
                        annot_keys = [str(k).lower() for k in annot.keys()]
                        if any(prop in annot_keys for prop in ["subtype", "link", "contents", "url"]):
                            has_annotations = True
                            break
                
                if has_annotations:
                    result["layers"].append({"layer": 5, "status": "OK"})
                    result["successful_layers"] += 1
                else:
                    # Check if tracking was intended (has tracking-related metadata)
                    docinfo = pdf.docinfo
                    has_tracking_intent = any(
                        "tracking" in str(k).lower() or "url" in str(k).lower() 
                        for k in docinfo.keys()
                    )
                    
                    if has_tracking_intent:
                        # Tracking was intended but annotation missing - FAIL
                        result["layers"].append({"layer": 5, "status": "FAIL"})
                        result["errors"].append({"layer": 5, "error": "Tracking annotation missing (tracking URL was intended)"})
                        result["corrupted"] = True
                    else:
                        # No tracking intended - OPTIONAL PASS
                        result["layers"].append({"layer": 5, "status": "OK"})
                        result["successful_layers"] += 1
            except Exception as e:
                result["layers"].append({"layer": 5, "status": "FAIL"})
                result["errors"].append({"layer": 5, "error": str(e)})
                result["corrupted"] = True
            
            # Layer 6: Embedded Original
            try:
                has_embedded = False
                if hasattr(pdf.Root, "Names") and hasattr(pdf.Root.Names, "EmbeddedFiles"):
                    embedded_files = pdf.Root.Names.EmbeddedFiles
                    if embedded_files and len(embedded_files.Names) > 0:
                        has_embedded = True
                
                if has_embedded:
                    result["layers"].append({"layer": 6, "status": "OK"})
                    result["successful_layers"] += 1
                else:
                    result["layers"].append({"layer": 6, "status": "FAIL"})
                    result["errors"].append({"layer": 6, "error": "Embedded original missing"})
                    result["corrupted"] = True
            except Exception as e:
                result["layers"].append({"layer": 6, "status": "FAIL"})
                result["errors"].append({"layer": 6, "error": str(e)})
                result["corrupted"] = True
            
            pdf.close()
            os.remove(temp_path)
            
        except Exception as e:
            result["pdf_valid"] = False
            result["corrupted"] = True
            result["errors"].append({"layer": 0, "error": f"Failed to open: {str(e)}"})
        
        results.append(result)
    
    return jsonify(results)

@app.route('/debug')
def debug():
    return jsonify({
        "SUPABASE_URL": os.environ.get('SUPABASE_URL', 'NOT SET'),
        "SUPABASE_ANON_KEY": os.environ.get('SUPABASE_ANON_KEY', 'NOT SET')[:10] + '...' if os.environ.get('SUPABASE_ANON_KEY') else 'NOT SET'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
