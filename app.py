"""
Cherax Language Translator - Web Version
Created by: Stefc3
GitHub: github.com/Stefcee/Cherax-JSON-Translator
Discord: dc.gg/chatify
"""

import os
import json
import io
import time
import uuid
import threading
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, send_file, jsonify, Response, session
from deep_translator import GoogleTranslator

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cherax_web_key_2026")

# ==================== DISCORD WEBHOOK & COUNTER ====================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK", "")
COUNTER_FILE = "cherax_translation_counter.json"

def load_counter():
    """Lädt Counter aus Datei (persistent)"""
    try:
        if os.path.exists(COUNTER_FILE):
            with open(COUNTER_FILE, 'r') as f:
                data = json.load(f)
                return data.get('count', 0)
    except Exception as e:
        print(f"⚠ Counter load error: {e}")
    return 0

def save_counter(count):
    """Speichert Counter in Datei"""
    try:
        with open(COUNTER_FILE, 'w') as f:
            json.dump({'count': count, 'last_updated': datetime.now().isoformat()}, f)
    except Exception as e:
        print(f"⚠ Counter save error: {e}")

# Globaler Counter laden
translation_count = load_counter()

def send_milestone_webhook(count):
    """Sendet Discord Notification bei Milestones"""
    milestones = [10, 25, 50, 100, 250, 500, 750, 1000, 2500, 5000]
    
    if count not in milestones or not DISCORD_WEBHOOK_URL:
        return
    
    embed = {
        "embeds": [{
            "title": "🚀 Cherax Translator - Milestone Reached!",
            "description": f"**{count} translations completed!** 🎉",
            "color": 4287245,  # Blau
            "fields": [
                {
                    "name": "📊 Total Translations",
                    "value": f"**{count}**",
                    "inline": True
                },
                {
                    "name": "⏰ Time",
                    "value": datetime.now().strftime("%d.%m.%Y %H:%M CET"),
                    "inline": True
                }
            ],
            "footer": {
                "text": "Cherax Translator • Created by Stefc3"
            },
            "timestamp": datetime.utcnow().isoformat()
        }]
    }
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=embed, timeout=5)
        if response.status_code == 204:
            print(f"✅ Milestone webhook sent: {count}")
        else:
            print(f"⚠ Webhook response: {response.status_code}")
    except Exception as e:
        print(f"⚠ Webhook failed: {e}")
# ==================== END WEBHOOK ====================

# Vollständige 56-Sprachen-Liste aus dem Original-Skript
LANGUAGES = {
    "Afrikaans": "af", "Albanian": "sq", "Arabic": "ar", "Armenian": "hy", "Azerbaijani": "az",
    "Basque": "eu", "Belarusian": "be", "Bengali": "bn", "Bulgarian": "bg", "Catalan": "ca",
    "Chinese (Simp)": "zh-CN", "Chinese (Trad)": "zh-TW", "Croatian": "hr", "Czech": "cs",
    "Danish": "da", "Dutch": "nl", "English": "en", "Estonian": "et", "Filipino": "tl",
    "Finnish": "fi", "French": "fr", "Galician": "gl", "Georgian": "ka", "German": "de",
    "Greek": "el", "Gujarati": "gu", "Haitian Creole": "ht", "Hebrew": "iw", "Hindi": "hi",
    "Hungarian": "hu", "Icelandic": "is", "Indonesian": "id", "Irish": "ga", "Italian": "it",
    "Japanese": "ja", "Kannada": "kn", "Korean": "ko", "Latvian": "lv", "Lithuanian": "lt",
    "Macedonian": "mk", "Malay": "ms", "Maltese": "mt", "Norwegian": "no", "Persian": "fa",
    "Polish": "pl", "Portuguese": "pt", "Romanian": "ro", "Russian": "ru", "Serbian": "sr",
    "Slovak": "sk", "Slovenian": "sl", "Spanish": "es", "Swahili": "sw", "Swedish": "sv",
    "Tamil": "ta", "Telugu": "te", "Thai": "th", "Turkish": "tr", "Ukrainian": "uk",
    "Urdu": "ur", "Vietnamese": "vi", "Welsh": "cy", "Yiddish": "yi"
}

# Temporärer Speicher für übersetzte Dateien mit Timestamp
translated_files = {}

def cleanup_old_files():
    """
    Background-Task: Löscht Dateien älter als 1 Stunde
    Verhindert Speicher-Overflow auf dem Server
    """
    while True:
        try:
            now = datetime.now()
            to_delete = []
            
            for file_id, file_data in translated_files.items():
                if 'timestamp' in file_data:
                    age = now - file_data['timestamp']
                    if age > timedelta(hours=1):
                        to_delete.append(file_id)
            
            for file_id in to_delete:
                del translated_files[file_id]
                print(f"🗑 Gelöscht: {file_id} (älter als 1 Stunde)")
            
            if to_delete:
                print(f"✅ Cleanup: {len(to_delete)} Dateien gelöscht")
        
        except Exception as e:
            print(f"⚠ Cleanup-Fehler: {e}")
        
        # Alle 10 Minuten prüfen
        time.sleep(600)

# Cleanup-Task im Hintergrund starten
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

def log_message(msg_type, text):
    """Erstellt formatierte Log-Nachricht mit Timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    return f"data: {json.dumps({'type': msg_type, 'message': f'[{timestamp}] {text}'})}\n\n"

def translate_with_sse(data, target_lang, target_lang_name):
    """
    Generator-Funktion für Server-Sent Events
    Sendet Live-Updates während der Übersetzung
    """
    translator = GoogleTranslator(source='auto', target=target_lang)
    translated_data = {}
    keys = list(data.keys())
    total_items = len(keys)
    separator = " ||| "
    batch_size = 50
    
    # Start-Logs
    yield log_message('info', '=' * 60)
    yield log_message('info', '🚀 Übersetzung gestartet...')
    yield log_message('info', f'📊 Gesamt: {total_items} Einträge')
    yield log_message('info', f'🌍 Zielsprache: {target_lang_name} ({target_lang})')
    yield log_message('info', '-' * 60)
    
    batch_count = 0
    i = 0
    
    while i < len(keys):
        batch_keys = keys[i:i + batch_size]
        
        try:
            if len(batch_keys) == 1:
                key = batch_keys[0]
                value = str(data[key])
                if value.strip():
                    translated_data[key] = translator.translate(value)
                else:
                    translated_data[key] = value
            else:
                # Batch-Übersetzung
                batch_texts = [str(data[k]) for k in batch_keys]
                combined = separator.join(batch_texts)
                
                translated_result = translator.translate(combined)
                parts = translated_result.split(separator.strip())
                
                if len(parts) == len(batch_keys):
                    for idx, key in enumerate(batch_keys):
                        translated_data[key] = parts[idx].strip() if parts[idx].strip() else data[key]
                else:
                    # Fallback: Einzelübersetzung
                    yield log_message('warning', '⚠ Batch mismatch, einzelne Übersetzung...')
                    for key in batch_keys:
                        value = str(data[key])
                        if value.strip():
                            try:
                                translated_data[key] = translator.translate(value)
                                time.sleep(0.3)
                            except Exception as e:
                                yield log_message('error', f'❌ Fehler bei "{key}": {str(e)}')
                                translated_data[key] = value
                        else:
                            translated_data[key] = value
            
            i += len(batch_keys)
            batch_count += 1
            progress = len(translated_data)
            percentage = int((progress / total_items) * 100)
            
            # Progress-Update alle 10 Batches oder bei 100%
            if batch_count % 10 == 0 or progress == total_items:
                yield log_message('progress', f'⏳ Fortschritt: {progress}/{total_items} ({percentage}%)')
                yield f"data: {json.dumps({'type': 'percentage', 'value': percentage})}\n\n"
            
            time.sleep(0.2)  # Rate-Limit-Schutz
            
        except Exception as e:
            yield log_message('error', f'❌ Fehler: {str(e)}')
            yield log_message('warning', f'⏸ Pausiert bei {len(translated_data)}/{total_items}')
            break
    
    # Erfolgsmeldung
    if len(translated_data) >= total_items:
        # Finale Daten zusammenstellen
        final_data = {k: translated_data.get(k, data[k]) for k in data.keys()}
        
        # Eindeutige ID für Download + Sprachcode + Timestamp speichern
        file_id = str(uuid.uuid4())
        lang_code_upper = target_lang.upper().replace('-', '_')
        translated_files[file_id] = {
            'data': final_data,
            'lang_code': lang_code_upper,
            'timestamp': datetime.now()
        }
        
        # ==================== WEBHOOK & COUNTER ====================
        global translation_count
        translation_count += 1
        save_counter(translation_count)
        
        # Webhook asynchron senden (blockiert nicht den Stream!)
        threading.Thread(
            target=send_milestone_webhook, 
            args=(translation_count,), 
            daemon=True
        ).start()
        # ==================== END WEBHOOK ====================
        
        yield log_message('info', '=' * 60)
        yield log_message('success', '✅ ÜBERSETZUNG ABGESCHLOSSEN!')
        yield log_message('info', f'📊 {total_items}/{total_items} Einträge übersetzt')
        yield log_message('info', f'🌍 Sprache: {target_lang_name}')
        yield f"data: {json.dumps({'type': 'complete', 'file_id': file_id, 'lang_code': lang_code_upper})}\n\n"
    else:
        yield log_message('error', '❌ Übersetzung unvollständig')
        yield f"data: {json.dumps({'type': 'error', 'message': 'Übersetzung fehlgeschlagen'})}\n\n"

@app.route('/', methods=['GET'])
def index():
    """Hauptseite mit Upload-Formular"""
    return render_template('index.html', languages=sorted(LANGUAGES.keys()))

@app.route('/translate', methods=['POST'])
def translate():
    """SSE-Endpoint für Echtzeit-Übersetzung"""
    try:
        file = request.files.get('file')
        target_lang_name = request.form.get('language')
        
        if not file or file.filename == '':
            return jsonify({'error': 'Keine Datei ausgewählt'}), 400
        
        if not target_lang_name or target_lang_name not in LANGUAGES:
            return jsonify({'error': 'Ungültige Sprache'}), 400
        
        # Dateigrößen-Check (Max 5MB)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 5 * 1024 * 1024:  # 5MB
            return jsonify({'error': 'Datei zu groß (max. 5MB)'}), 400
        
        # JSON laden
        try:
            content = json.load(file)
        except json.JSONDecodeError:
            return jsonify({'error': 'Ungültige JSON-Datei'}), 400
        
        if not isinstance(content, dict):
            return jsonify({'error': 'JSON muss ein Key-Value-Objekt sein'}), 400
        
        target_code = LANGUAGES[target_lang_name]
        
        # SSE-Stream starten
        return Response(
            translate_with_sse(content, target_code, target_lang_name),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )
        
    except Exception as e:
        print(f"Server error: {e}")
        return jsonify({'error': f'Serverfehler: {str(e)}'}), 500

@app.route('/download/<file_id>')
def download(file_id):
    """Download der übersetzten Datei"""
    if file_id not in translated_files:
        return jsonify({'error': 'Datei nicht gefunden oder abgelaufen'}), 404
    
    try:
        file_info = translated_files[file_id]
        data = file_info['data']
        lang_code = file_info['lang_code']
        
        # JSON erstellen
        output = io.BytesIO()
        output.write(json.dumps(data, indent=4, ensure_ascii=False).encode('utf-8'))
        output.seek(0)
        
        # Nach Download aus Speicher löschen
        del translated_files[file_id]
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f'TranslationFile_{lang_code}.json',
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health-Check für Render.com"""
    return jsonify({
        'status': 'ok', 
        'languages': len(LANGUAGES),
        'cached_files': len(translated_files),
        'total_translations': translation_count
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Cherax Translator starting... (Total translations: {translation_count})")
    app.run(host='0.0.0.0', port=port, debug=False)
