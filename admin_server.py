from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def admin():
    with open('admin.html', 'r') as f:
        html = f.read()
    
    # Inject env vars
    html = html.replace("'YOUR_SUPABASE_URL'", f"'{os.environ.get('SUPABASE_URL', '')}'")
    html = html.replace("'YOUR_SUPABASE_ANON_KEY'", f"'{os.environ.get('SUPABASE_ANON_KEY', '')}'")
    
    return html

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
