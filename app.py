from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
from datetime import datetime

app = Flask(__name__)
# Get database URL from environment, default to local database
db_url = os.environ.get('DATABASE_URL', 'sqlite:///ranqr.db')

# Ensure database directory exists before setting config
if db_url.startswith('sqlite:///'):
    # Extract database path from SQLite URI
    # sqlite:///path -> path, sqlite:////path -> /path (absolute)
    if db_url.startswith('sqlite:////'):
        # Absolute path format: sqlite:////absolute/path -> /absolute/path
        db_path = '/' + db_url[12:]  # Remove 'sqlite:////' and add leading /
    else:
        # Relative path format: sqlite:///relative/path -> relative/path
        db_path = db_url[10:]  # Remove 'sqlite:///'
        # If it has directory separators, make it absolute relative to app directory
        if '/' in db_path or '\\' in db_path:
            if not os.path.isabs(db_path):
                db_path = os.path.join(os.path.dirname(__file__), db_path)
            # Convert to absolute path format (4 slashes)
            db_url = f'sqlite:///{db_path}'
    
    # Ensure parent directory exists
    if db_path:
        db_dir = os.path.dirname(db_path)
        if db_dir and db_dir != '/':
            try:
                os.makedirs(db_dir, exist_ok=True)
            except (OSError, PermissionError) as e:
                # Log but don't fail - might be permission issue
                print(f"Warning: Could not create database directory {db_dir}: {e}")

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
CORS(app)

# Database Models
class Collection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    items = db.relationship('Item', backref='collection', lazy=True, cascade='all, delete-orphan')
    comparisons = db.relationship('Comparison', backref='collection', lazy=True, cascade='all, delete-orphan')

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(db.Integer, db.ForeignKey('collection.id'), nullable=False)
    name = db.Column(db.String(500), nullable=False)
    media_link = db.Column(db.String(1000), nullable=True)  # YouTube or other media link
    points = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

class Comparison(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(db.Integer, db.ForeignKey('collection.id'), nullable=False)
    item1_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    item2_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    result = db.Column(db.String(20), nullable=True)  # 'item1', 'item2', or 'tie'
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    __table_args__ = (db.UniqueConstraint('item1_id', 'item2_id', name='unique_comparison'),)

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/collections', methods=['GET'])
def get_collections():
    collections = Collection.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'item_count': len(c.items),
        'created_at': c.created_at.isoformat() if c.created_at else None
    } for c in collections])

@app.route('/api/collections', methods=['POST'])
def create_collection():
    data = request.json
    collection = Collection(name=data['name'])
    db.session.add(collection)
    db.session.commit()
    
    items_text = data.get('items', '')
    items_list = [item.strip() for item in items_text.split('\n') if item.strip()]
    
    for item_name in items_list:
        item = Item(collection_id=collection.id, name=item_name)
        db.session.add(item)
    
    db.session.commit()
    return jsonify({'id': collection.id, 'name': collection.name}), 201

@app.route('/api/collections/<int:collection_id>', methods=['GET'])
def get_collection(collection_id):
    collection = Collection.query.get_or_404(collection_id)
    items = sorted(collection.items, key=lambda x: x.points, reverse=True)
    
    return jsonify({
        'id': collection.id,
        'name': collection.name,
        'items': [{
            'id': item.id,
            'name': item.name,
            'media_link': item.media_link,
            'points': item.points
        } for item in items],
        'comparisons_count': len(collection.comparisons)
    })

@app.route('/api/collections/<int:collection_id>/matchup', methods=['GET'])
def get_next_matchup(collection_id):
    collection = Collection.query.get_or_404(collection_id)
    items = collection.items
    
    if len(items) < 2:
        return jsonify({'error': 'Need at least 2 items for a matchup'}), 400
    
    # Get smart matchup using merge-sort-like approach
    matchup = get_smart_matchup(collection)
    
    if matchup:
        return jsonify({
            'item1': {
                'id': matchup[0].id,
                'name': matchup[0].name,
                'media_link': matchup[0].media_link
            },
            'item2': {
                'id': matchup[1].id,
                'name': matchup[1].name,
                'media_link': matchup[1].media_link
            }
        })
    else:
        return jsonify({'message': 'All comparisons completed'}), 200

@app.route('/api/collections/<int:collection_id>/matchup', methods=['POST'])
def submit_matchup_result(collection_id):
    collection = Collection.query.get_or_404(collection_id)
    data = request.json
    
    item1_id = data['item1_id']
    item2_id = data['item2_id']
    winner = data.get('winner')  # 'item1', 'item2', or 'tie'
    
    # Ensure consistent ordering (always store smaller ID first)
    if item1_id > item2_id:
        item1_id, item2_id = item2_id, item1_id
        if winner == 'item1':
            winner = 'item2'
        elif winner == 'item2':
            winner = 'item1'
    
    # Check if comparison already exists
    comparison = Comparison.query.filter_by(
        collection_id=collection_id,
        item1_id=item1_id,
        item2_id=item2_id
    ).first()
    
    old_result = None
    if comparison:
        # Update existing comparison
        old_result = comparison.result
        comparison.result = winner
    else:
        # Create new comparison
        comparison = Comparison(
            collection_id=collection_id,
            item1_id=item1_id,
            item2_id=item2_id,
            result=winner
        )
        db.session.add(comparison)
    
    # Update points
    item1 = db.session.get(Item, item1_id)
    item2 = db.session.get(Item, item2_id)
    
    # Remove old point adjustments if updating
    if old_result:
        if old_result == 'item1':
            item1.points -= 1
            item2.points += 1
        elif old_result == 'item2':
            item1.points += 1
            item2.points -= 1
        elif old_result == 'tie':
            # Ties don't affect points, but we track them
            pass
    
    # Apply new point adjustments
    if winner == 'item1':
        item1.points += 1
        item2.points -= 1
    elif winner == 'item2':
        item1.points -= 1
        item2.points += 1
    elif winner == 'tie':
        # Ties don't change points
        pass
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/collections/<int:collection_id>/items', methods=['POST'])
def add_items(collection_id):
    collection = Collection.query.get_or_404(collection_id)
    data = request.json
    
    items_text = data.get('items', '')
    items_list = [item.strip() for item in items_text.split('\n') if item.strip()]
    
    for item_name in items_list:
        item = Item(collection_id=collection_id, name=item_name, media_link=None)
        db.session.add(item)
    
    db.session.commit()
    return jsonify({'success': True, 'added': len(items_list)})

def normalize_youtube_url(url):
    """Normalize YouTube URLs - convert video IDs to full URLs."""
    if not url:
        return None
    
    url = url.strip()
    
    # If it's already a full URL, return as-is
    if url.startswith('http://') or url.startswith('https://'):
        return url
    
    # Check if it looks like a YouTube video ID (11 characters, alphanumeric + _ and -)
    import re
    video_id_pattern = re.compile(r'^[a-zA-Z0-9_-]{11}$')
    if video_id_pattern.match(url):
        # Convert video ID to full YouTube URL
        return f'https://www.youtube.com/watch?v={url}'
    
    # If it's not a video ID and doesn't have a protocol, return as-is
    # (might be invalid, but let user fix it)
    return url

@app.route('/api/items/<int:item_id>', methods=['PUT', 'PATCH'])
def update_item(item_id):
    item = Item.query.get_or_404(item_id)
    data = request.json
    
    if 'name' in data:
        item.name = data['name'].strip()
    if 'media_link' in data:
        # Allow empty string to clear media link
        media_link = data['media_link'].strip() if data['media_link'] else None
        if media_link:
            # Normalize YouTube URLs
            media_link = normalize_youtube_url(media_link)
        item.media_link = media_link
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'item': {
            'id': item.id,
            'name': item.name,
            'media_link': item.media_link,
            'points': item.points
        }
    })

@app.route('/api/collections/<int:collection_id>', methods=['DELETE'])
def delete_collection(collection_id):
    collection = Collection.query.get_or_404(collection_id)
    db.session.delete(collection)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/collections/<int:collection_id>/export', methods=['GET'])
def export_collection(collection_id):
    """Export a collection as JSON including all items, comparisons, and voting data."""
    collection = Collection.query.get_or_404(collection_id)
    
    # Build export data
    # Get item names for comparisons
    items_dict = {item.id: item.name for item in collection.items}
    
    export_data = {
        'version': '1.0',
        'exported_at': datetime.utcnow().isoformat(),
        'collection': {
            'name': collection.name,
            'created_at': collection.created_at.isoformat() if collection.created_at else None
        },
        'items': [{
            'name': item.name,
            'media_link': item.media_link,
            'points': item.points
        } for item in collection.items],
        'comparisons': [{
            'item1_name': items_dict.get(comp.item1_id),
            'item2_name': items_dict.get(comp.item2_id),
            'result': comp.result
        } for comp in collection.comparisons if items_dict.get(comp.item1_id) and items_dict.get(comp.item2_id)]
    }
    
    return jsonify(export_data)

@app.route('/api/collections/import', methods=['POST'])
def import_collection():
    """Import a collection from JSON blob, restoring items, comparisons, and voting data."""
    data = request.json
    
    if not data or 'collection' not in data or 'items' not in data:
        return jsonify({'error': 'Invalid import data. Expected collection, items, and optionally comparisons.'}), 400
    
    # Create new collection
    collection = Collection(name=data['collection']['name'])
    db.session.add(collection)
    db.session.flush()  # Get the collection ID
    
    # Create name to item mapping for comparisons
    name_to_item = {}
    
    # Import items
    for item_data in data['items']:
        item = Item(
            collection_id=collection.id,
            name=item_data['name'],
            media_link=item_data.get('media_link'),
            points=item_data.get('points', 0)
        )
        db.session.add(item)
        name_to_item[item_data['name']] = item
    
    db.session.flush()  # Get item IDs
    
    # Import comparisons if they exist
    comparisons_imported = 0
    if 'comparisons' in data:
        for comp_data in data['comparisons']:
            item1_name = comp_data.get('item1_name')
            item2_name = comp_data.get('item2_name')
            result = comp_data.get('result')
            
            if not item1_name or not item2_name or not result:
                continue
            
            item1 = name_to_item.get(item1_name)
            item2 = name_to_item.get(item2_name)
            
            # Skip if either item is missing or if it's the same item
            if not item1 or not item2 or item1.id == item2.id:
                continue
            
            # Ensure consistent ordering (smaller ID first)
            item1_id, item2_id = item1.id, item2.id
            if item1_id > item2_id:
                item1_id, item2_id = item2_id, item1_id
                # Adjust result if we swapped
                if result == 'item1':
                    result = 'item2'
                elif result == 'item2':
                    result = 'item1'
            
            comparison = Comparison(
                collection_id=collection.id,
                item1_id=item1_id,
                item2_id=item2_id,
                result=result
            )
            db.session.add(comparison)
            comparisons_imported += 1
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'collection_id': collection.id,
        'items_imported': len(data['items']),
        'comparisons_imported': comparisons_imported
    }), 201

# Smart matchup algorithm (merge-sort-like approach)
def get_smart_matchup(collection):
    """
    Uses a smart approach to find the next comparison to make.
    Prioritizes comparisons that will help resolve the ranking order.
    Similar to merge sort, we focus on items that are close in rank.
    """
    items = list(collection.items)
    comparisons = {frozenset({c.item1_id, c.item2_id}): c.result 
                   for c in collection.comparisons}
    
    if len(items) < 2:
        return None
    
    # Get all possible matchups
    possible_matchups = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            item1, item2 = items[i], items[j]
            matchup_key = frozenset({item1.id, item2.id})
            
            # Skip if already compared
            if matchup_key in comparisons:
                continue
            
            # Calculate priority: prefer comparing items with similar scores
            score_diff = abs(item1.points - item2.points)
            # Lower score difference = higher priority (closer in rank)
            # Also prefer items that have fewer comparisons so far
            
            item1_comparisons = sum(1 for c in comparisons.keys() if item1.id in c)
            item2_comparisons = sum(1 for c in comparisons.keys() if item2.id in c)
            total_comparisons = item1_comparisons + item2_comparisons
            
            # Priority: lower score difference and fewer total comparisons
            priority = score_diff * 1000 - total_comparisons
            
            possible_matchups.append((priority, (item1, item2)))
    
    if not possible_matchups:
        return None
    
    # Sort by priority (lower is better)
    possible_matchups.sort(key=lambda x: x[0])
    
    # Return the highest priority matchup
    return possible_matchups[0][1]

# Initialize database
with app.app_context():
    db.create_all()
    
    # Migration: Add media_link column if it doesn't exist (for existing databases)
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('item')]
        if 'media_link' not in columns:
            # Add the column if it doesn't exist
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE item ADD COLUMN media_link VARCHAR(1000)'))
                conn.commit()
            print("✓ Added media_link column to existing database")
    except Exception as e:
        # If migration fails, it's likely a new database or the column already exists
        pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

