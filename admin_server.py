from flask import Flask, jsonify, request
import os
import hashlib, hmac, base64, zlib

app = Flask(__name__)

class PDFDecryptor:
    def __init__(self, master_key=b"your_master_key"):
        self.master_key = master_key
    
    def decrypt(self, encrypted_data):
        trail = {"layers": []}
        data = encrypted_data
        
        # Layer 1: Base64
        try:
            data = base64.b64decode(data)
            trail["layers"].append({"layer": 1, "status": "OK", "size": len(data)})
        except Exception as e:
            trail["layers"].append({"layer": 1, "status": "FAIL", "error": str(e)})
            return None, trail
        
        # Layer 2: XOR
        try:
            key = hashlib.sha256(self.master_key + b"2").digest()
            data = bytes(a ^ b for a, b in zip(data, key * (len(data)//len(key)+1)))
            trail["layers"].append({"layer": 2, "status": "OK", "size": len(data)})
        except Exception as e:
            trail["layers"].append({"layer": 2, "status": "FAIL", "error": str(e)})
            return None, trail
        
        # Layer 3: HMAC
        try:
            stored_hmac = data[-64:].decode()
            payload = data[:-64]
            key = hashlib.sha256(self.master_key + b"3").digest()
            computed = hmac.new(key, payload, hashlib.sha256).hexdigest()
            if computed != stored_hmac:
                trail["layers"].append({"layer": 3, "status": "FAIL", "error": "HMAC mismatch"})
                return None, trail
            data = payload
            trail["layers"].append({"layer": 3, "status": "OK", "size": len(data)})
        except Exception as e:
            trail["layers"].append({"layer": 3, "status": "FAIL", "error": str(e)})
            return None, trail
        
        # Layer 4: Decrypt
        try:
            key = hashlib.sha256(self.master_key + b"4").digest()
            decrypted = bytearray(data)
            for i in range(len(decrypted)):
                decrypted[i] ^= key[i % len(key)]
                decrypted[i] = (decrypted[i] - (i % 256)) % 256
            data = bytes(decrypted)
            trail["layers"].append({"layer": 4, "status": "OK", "size": len(data)})
        except Exception as e:
            trail["layers"].append({"layer": 4, "status": "FAIL", "error": str(e)})
            return None, trail
        
        # Layer 5: Decompress
        try:
            data = zlib.decompress(data)
            trail["layers"].append({"layer": 5, "status": "OK", "size": len(data)})
        except Exception as e:
            trail["layers"].append({"layer": 5, "status": "FAIL", "error": str(e)})
            return None, trail
        
        # Layer 6: Checksum
        try:
            stored_checksum = data[-64:].decode()
            pdf_data = data[:-64]
            computed = hashlib.sha256(pdf_data).hexdigest()
            if computed != stored_checksum:
                trail["layers"].append({"layer": 6, "status": "FAIL", "error": "Checksum mismatch"})
                return None, trail
            trail["layers"].append({"layer": 6, "status": "OK", "size": len(pdf_data)})
        except Exception as e:
            trail["layers"].append({"layer": 6, "status": "FAIL", "error": str(e)})
            return None, trail
        
        return pdf_data, trail

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
    
    files = request.files.getlist('files')
    decryptor = PDFDecryptor(master_key=os.environ.get('PDF_MASTER_KEY', 'your_master_key').encode())
    
    results = []
    for file in files:
        encrypted_data = file.read()
        pdf_data, trail = decryptor.decrypt(encrypted_data)
        
        is_corrupted = pdf_data is None
        is_pdf_valid = pdf_data and pdf_data.startswith(b'%PDF') if pdf_data else False
        successful_layers = sum(1 for layer in trail["layers"] if layer["status"] == "OK")
        
        errors = [{"layer": l["layer"], "error": l.get("error", "")} for l in trail["layers"] if l["status"] == "FAIL"]
        
        results.append({
            "filename": file.filename,
            "corrupted": is_corrupted or not is_pdf_valid,
            "pdf_valid": is_pdf_valid,
            "successful_layers": successful_layers,
            "layers": trail["layers"],
            "errors": errors
        })
    
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
