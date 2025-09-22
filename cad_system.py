#!/usr/bin/env python3
"""
Computer-Aided Dispatch (CAD) System
A comprehensive emergency services dispatch system with units, calls, BOLOs, and notes.
"""

import json
import os
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_socketio import SocketIO, emit
import sqlite3
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cad-system-secret-key-2024'
socketio = SocketIO(app, cors_allowed_origins="*")

# Database setup
DATABASE = 'cad_system.db'

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables"""
    conn = get_db()
    cursor = conn.cursor()

    # Units table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS units (
            id TEXT PRIMARY KEY,
            unit_number TEXT UNIQUE NOT NULL,
            unit_type TEXT NOT NULL,
            status TEXT DEFAULT 'Available',
            location TEXT,
            assigned_call_id TEXT,
            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assigned_call_id) REFERENCES calls (id)
        )
    ''')

    # Calls table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calls (
            id TEXT PRIMARY KEY,
            call_number TEXT UNIQUE NOT NULL,
            priority TEXT DEFAULT 'Medium',
            call_type TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'New',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            assigned_unit_id TEXT,
            reporter_name TEXT,
            reporter_phone TEXT,
            FOREIGN KEY (assigned_unit_id) REFERENCES units (id)
        )
    ''')

    # BOLOs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bolos (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            bolo_type TEXT NOT NULL,
            priority TEXT DEFAULT 'Medium',
            status TEXT DEFAULT 'Active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            created_by TEXT
        )
    ''')

    # Notes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            call_id TEXT,
            unit_id TEXT,
            note_type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            FOREIGN KEY (call_id) REFERENCES calls (id),
            FOREIGN KEY (unit_id) REFERENCES units (id)
        )
    ''')

    # Status codes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS status_codes (
            id TEXT PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL
        )
    ''')

    # Insert default status codes
    default_codes = [
        ('10-4', 'Message Received/Acknowledged', 'Communication'),
        ('10-6', 'Busy', 'Status'),
        ('10-7', 'Out of Service', 'Status'),
        ('10-8', 'In Service', 'Status'),
        ('10-20', 'Location', 'Information'),
        ('10-28', 'Vehicle Information', 'Information'),
        ('10-97', 'Arrived at Scene', 'Status'),
        ('10-98', 'Finished Assignment', 'Status'),
        ('Code 1', 'Normal Response', 'Priority'),
        ('Code 2', 'Urgent Response', 'Priority'),
        ('Code 3', 'Emergency Response', 'Priority'),
    ]

    cursor.executemany('INSERT OR IGNORE INTO status_codes (code, description, category) VALUES (?, ?, ?)', default_codes)

    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # For demo purposes, we'll skip actual auth
        # In production, implement proper authentication
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
@login_required
def index():
    return render_template('cad_dashboard.html')

@app.route('/api/units')
@login_required
def get_units():
    conn = get_db()
    units = conn.execute('SELECT * FROM units ORDER BY unit_number').fetchall()
    conn.close()
    return jsonify([dict(unit) for unit in units])

@app.route('/api/units', methods=['POST'])
@login_required
def create_unit():
    data = request.json
    unit_id = str(uuid.uuid4())

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO units (id, unit_number, unit_type, status, location)
        VALUES (?, ?, ?, ?, ?)
    ''', (unit_id, data['unit_number'], data['unit_type'], data.get('status', 'Available'), data.get('location', '')))

    conn.commit()
    conn.close()

    socketio.emit('unit_update', {'action': 'created', 'unit_id': unit_id})
    return jsonify({'id': unit_id, 'message': 'Unit created successfully'})

@app.route('/api/units/<unit_id>', methods=['PUT'])
@login_required
def update_unit(unit_id):
    data = request.json

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE units
        SET status = ?, location = ?, last_update = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (data['status'], data.get('location', ''), unit_id))

    conn.commit()
    conn.close()

    socketio.emit('unit_update', {'action': 'updated', 'unit_id': unit_id})
    return jsonify({'message': 'Unit updated successfully'})

@app.route('/api/calls')
@login_required
def get_calls():
    conn = get_db()
    calls = conn.execute('SELECT * FROM calls ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(call) for call in calls])

@app.route('/api/calls', methods=['POST'])
@login_required
def create_call():
    data = request.json
    call_id = str(uuid.uuid4())
    call_number = f"CALL-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO calls (id, call_number, priority, call_type, location, description, status, reporter_name, reporter_phone)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (call_id, call_number, data['priority'], data['call_type'], data['location'],
          data.get('description', ''), data.get('status', 'New'), data.get('reporter_name', ''),
          data.get('reporter_phone', '')))

    conn.commit()
    conn.close()

    socketio.emit('call_update', {'action': 'created', 'call_id': call_id})
    return jsonify({'id': call_id, 'call_number': call_number, 'message': 'Call created successfully'})

@app.route('/api/calls/<call_id>', methods=['DELETE'])
@login_required
def delete_call(call_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM calls WHERE id = ?', (call_id,))
    conn.commit()
    conn.close()

    socketio.emit('call_update', {'action': 'deleted', 'call_id': call_id})
    return jsonify({'message': 'Call deleted successfully'})

@app.route('/api/bolos')
@login_required
def get_bolos():
    conn = get_db()
    bolos = conn.execute('SELECT * FROM bolos ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(bolo) for bolo in bolos])

@app.route('/api/bolos', methods=['POST'])
@login_required
def create_bolo():
    data = request.json
    bolo_id = str(uuid.uuid4())

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO bolos (id, title, description, bolo_type, priority, status, expires_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (bolo_id, data['title'], data['description'], data['bolo_type'],
          data.get('priority', 'Medium'), data.get('status', 'Active'),
          data.get('expires_at'), data.get('created_by', 'Dispatcher')))

    conn.commit()
    conn.close()

    socketio.emit('bolo_update', {'action': 'created', 'bolo_id': bolo_id})
    return jsonify({'id': bolo_id, 'message': 'BOLO created successfully'})

@app.route('/api/bolos/<bolo_id>', methods=['DELETE'])
@login_required
def delete_bolo(bolo_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM bolos WHERE id = ?', (bolo_id,))
    conn.commit()
    conn.close()

    socketio.emit('bolo_update', {'action': 'deleted', 'bolo_id': bolo_id})
    return jsonify({'message': 'BOLO deleted successfully'})

@app.route('/api/notes')
@login_required
def get_notes():
    conn = get_db()
    notes = conn.execute('SELECT * FROM notes ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(note) for note in notes])

@app.route('/api/notes', methods=['POST'])
@login_required
def create_note():
    data = request.json
    note_id = str(uuid.uuid4())

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO notes (id, call_id, unit_id, note_type, content, created_by)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (note_id, data.get('call_id'), data.get('unit_id'), data['note_type'],
          data['content'], data.get('created_by', 'Dispatcher')))

    conn.commit()
    conn.close()

    socketio.emit('note_update', {'action': 'created', 'note_id': note_id})
    return jsonify({'id': note_id, 'message': 'Note created successfully'})

@app.route('/api/notes/<note_id>', methods=['DELETE'])
@login_required
def delete_note(note_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM notes WHERE id = ?', (note_id,))
    conn.commit()
    conn.close()

    socketio.emit('note_update', {'action': 'deleted', 'note_id': note_id})
    return jsonify({'message': 'Note deleted successfully'})

@app.route('/api/status-codes')
@login_required
def get_status_codes():
    conn = get_db()
    codes = conn.execute('SELECT * FROM status_codes ORDER BY category, code').fetchall()
    conn.close()
    return jsonify([dict(code) for code in codes])

# SocketIO events
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {'message': 'Connected to CAD System'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('get_units')
def handle_get_units():
    """Handle request for units data"""
    conn = get_db()
    units = conn.execute('SELECT * FROM units ORDER BY unit_number').fetchall()
    conn.close()
    emit('units_data', [dict(unit) for unit in units])

@socketio.on('get_calls')
def handle_get_calls():
    """Handle request for calls data"""
    conn = get_db()
    calls = conn.execute('SELECT * FROM calls ORDER BY created_at DESC').fetchall()
    conn.close()
    emit('calls_data', [dict(call) for call in calls])

@socketio.on('get_bolos')
def handle_get_bolos():
    """Handle request for BOLOs data"""
    conn = get_db()
    bolos = conn.execute('SELECT * FROM bolos ORDER BY created_at DESC').fetchall()
    conn.close()
    emit('bolos_data', [dict(bolo) for bolo in bolos])

@socketio.on('get_notes')
def handle_get_notes():
    """Handle request for notes data"""
    conn = get_db()
    notes = conn.execute('SELECT * FROM notes ORDER BY created_at DESC').fetchall()
    conn.close()
    emit('notes_data', [dict(note) for note in notes])

@socketio.on('add_unit')
def handle_add_unit(data):
    """Handle adding a new unit"""
    print(f"🔧 DEBUG: Received add_unit event with data: {data}")

    try:
        # Validate required fields
        if not data.get('number') or not data.get('type'):
            print(f"❌ DEBUG: Missing required fields - number: {data.get('number')}, type: {data.get('type')}")
            emit('error', {'message': 'Unit number and type are required'})
            return

        conn = get_db()
        cursor = conn.cursor()

        # Check if unit already exists
        cursor.execute('SELECT id FROM units WHERE unit_number = ?', (data['number'],))
        existing_unit = cursor.fetchone()

        if existing_unit:
            print(f"❌ DEBUG: Unit with number '{data['number']}' already exists")
            emit('error', {'message': f'Unit with number "{data["number"]}" already exists. Please use a different unit number.'})
            conn.close()
            return

        unit_id = str(uuid.uuid4())
        print(f"🔧 DEBUG: Generated unit_id: {unit_id}")

        print(f"🔧 DEBUG: Inserting unit into database...")
        cursor.execute('''
            INSERT INTO units (id, unit_number, unit_type, status, location)
            VALUES (?, ?, ?, ?, ?)
        ''', (unit_id, data['number'], data['type'], data.get('status', 'Available'), data.get('location', '')))

        conn.commit()
        print(f"✅ DEBUG: Successfully inserted unit into database")
        conn.close()

        # Broadcast the new unit to all clients
        print(f"🔧 DEBUG: Broadcasting units_data to all clients...")
        units_data = [dict(unit) for unit in get_db().execute('SELECT * FROM units ORDER BY unit_number').fetchall()]
        print(f"🔧 DEBUG: Retrieved {len(units_data)} units from database")
        emit('units_data', units_data, broadcast=True)
        emit('unit_update', {'action': 'created', 'unit_id': unit_id}, broadcast=True)
        print(f"✅ DEBUG: Successfully broadcast unit creation")

    except Exception as e:
        print(f"❌ DEBUG: Error adding unit: {str(e)}")
        import traceback
        print(f"❌ DEBUG: Traceback: {traceback.format_exc()}")
        emit('error', {'message': f'Error adding unit: {str(e)}'})

@socketio.on('add_call')
def handle_add_call(data):
    """Handle adding a new call"""
    call_id = str(uuid.uuid4())
    call_number = f"CALL-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO calls (id, call_number, priority, call_type, location, description, status, reporter_name, reporter_phone)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (call_id, call_number, data['priority'], data['type'], data['location'],
          data.get('description', ''), data.get('status', 'New'), data.get('reporter_name', ''),
          data.get('reporter_phone', '')))

    conn.commit()
    conn.close()

    # Broadcast the new call to all clients
    emit('calls_data', [dict(call) for call in get_db().execute('SELECT * FROM calls ORDER BY created_at DESC').fetchall()], broadcast=True)
    emit('call_update', {'action': 'created', 'call_id': call_id}, broadcast=True)

@socketio.on('add_note')
def handle_add_note(data):
    """Handle adding a new note"""
    note_id = str(uuid.uuid4())

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO notes (id, call_id, unit_id, note_type, content, created_by)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (note_id, data.get('call_id'), data.get('unit_id'), data['type'],
          data['content'], data.get('created_by', 'Dispatcher')))

    conn.commit()
    conn.close()

    # Broadcast the new note to all clients
    emit('notes_data', [dict(note) for note in get_db().execute('SELECT * FROM notes ORDER BY created_at DESC').fetchall()], broadcast=True)
    emit('note_update', {'action': 'created', 'note_id': note_id}, broadcast=True)

@socketio.on('add_bolo')
def handle_add_bolo(data):
    """Handle adding a new BOLO"""
    bolo_id = str(uuid.uuid4())

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO bolos (id, title, description, bolo_type, priority, status, expires_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (bolo_id, data['title'], data['description'], data['type'],
          data.get('priority', 'Medium'), data.get('status', 'Active'),
          data.get('expires_at'), data.get('created_by', 'Dispatcher')))

    conn.commit()
    conn.close()

    # Broadcast the new BOLO to all clients
    emit('bolos_data', [dict(bolo) for bolo in get_db().execute('SELECT * FROM bolos ORDER BY created_at DESC').fetchall()], broadcast=True)
    emit('bolo_update', {'action': 'created', 'bolo_id': bolo_id}, broadcast=True)

if __name__ == '__main__':
    print("🚨 CAD System Starting...")
    print("📍 Dashboard: http://localhost:5000")
    print("🔗 WebSocket: ws://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
