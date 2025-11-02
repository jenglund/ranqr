from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
from datetime import datetime
import urllib.parse

app = Flask(__name__)

# Check if we're in testing mode FIRST - before setting up database
# This prevents tests from ever touching the production database
is_testing = os.environ.get('TESTING') == '1'

# Get database URL from environment, default to local database
# If testing, use in-memory database to completely isolate tests
if is_testing:
    db_url = 'sqlite:///:memory:'
    app.config['TESTING'] = True
else:
    db_url = os.environ.get('DATABASE_URL', 'sqlite:///ranqr.db')

# Ensure database directory exists before setting config
# SKIP file system operations when testing (use in-memory database)
if not is_testing and db_url.startswith('sqlite:///') and ':memory:' not in db_url:
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
    search_prefix = db.Column(db.String(200), nullable=True)  # YouTube search prefix for items
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
        'search_prefix': c.search_prefix,
        'item_count': len(c.items),
        'created_at': c.created_at.isoformat() if c.created_at else None
    } for c in collections])

@app.route('/api/collections', methods=['POST'])
def create_collection():
    data = request.json
    name = data.get('name', '').strip()
    search_prefix = data.get('search_prefix', '').strip() or None
    
    if not name:
        return jsonify({'error': 'Collection name is required'}), 400
    
    collection = Collection(name=name, search_prefix=search_prefix)
    db.session.add(collection)
    db.session.flush()  # Get the collection ID
    
    items_text = data.get('items', '').strip()
    items_list = [item.strip() for item in items_text.split('\n') if item.strip()]
    
    for item_name in items_list:
        item = Item(collection_id=collection.id, name=item_name)
        db.session.add(item)
    
    db.session.commit()
    return jsonify({'id': collection.id, 'name': collection.name, 'search_prefix': collection.search_prefix}), 201

def calculate_sub_scores(items_in_group, comparisons):
    """
    Calculate sub-scores for items within a tied group based on comparisons
    that involve ONLY items within that group.
    
    Args:
        items_in_group: List of Item objects with the same main score
        comparisons: List of all Comparison objects for the collection
    
    Returns:
        Dictionary mapping item_id to sub_score (int)
    """
    if len(items_in_group) <= 1:
        # No comparisons possible with 0 or 1 items
        return {item.id: 0 for item in items_in_group}
    
    # Create set of item IDs in this group for fast lookup
    group_item_ids = {item.id for item in items_in_group}
    
    # Initialize sub-scores to 0
    sub_scores = {item.id: 0 for item in items_in_group}
    
    # Process comparisons that involve ONLY items within this group
    for comp in comparisons:
        # Check if both items are in the group
        if comp.item1_id in group_item_ids and comp.item2_id in group_item_ids:
            # Calculate sub-score impact (same as main scoring: +1 win, -1 loss, 0 tie)
            if comp.result == 'item1':
                sub_scores[comp.item1_id] += 1
                sub_scores[comp.item2_id] -= 1
            elif comp.result == 'item2':
                sub_scores[comp.item1_id] -= 1
                sub_scores[comp.item2_id] += 1
            # Ties don't affect sub-scores (already 0)
    
    return sub_scores

def sort_items_with_tie_breaking(items, comparisons):
    """
    Sort items by points, using sub-scores to break ties.
    
    Args:
        items: List of Item objects to sort
        comparisons: List of Comparison objects for the collection
    
    Returns:
        Sorted list of Item objects
    """
    # First, sort by main points (descending)
    items_by_points = {}
    for item in items:
        if item.points not in items_by_points:
            items_by_points[item.points] = []
        items_by_points[item.points].append(item)
    
    # Sort point groups in descending order
    sorted_points = sorted(items_by_points.keys(), reverse=True)
    
    # Build final sorted list
    sorted_items = []
    for points in sorted_points:
        group = items_by_points[points]
        
        if len(group) == 1:
            # No tie-breaking needed
            sorted_items.append(group[0])
        else:
            # Calculate sub-scores for this tied group
            sub_scores = calculate_sub_scores(group, comparisons)
            
            # Sort within group by sub-score (descending), then by ID for stability
            group.sort(key=lambda x: (sub_scores[x.id], -x.id), reverse=True)
            sorted_items.extend(group)
    
    return sorted_items

@app.route('/api/collections/<int:collection_id>', methods=['GET'])
def get_collection(collection_id):
    collection = Collection.query.get_or_404(collection_id)
    # Use tie-breaking sorting algorithm
    items = sort_items_with_tie_breaking(list(collection.items), list(collection.comparisons))
    
    return jsonify({
        'id': collection.id,
        'name': collection.name,
        'search_prefix': collection.search_prefix,
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
    
    # Check if specific item IDs were requested (query parameters)
    item1_id = request.args.get('item1_id', type=int)
    item2_id = request.args.get('item2_id', type=int)
    
    # If specific items requested, return that matchup
    if item1_id and item2_id:
        item1 = db.session.get(Item, item1_id)
        item2 = db.session.get(Item, item2_id)
        
        if not item1 or not item2:
            return jsonify({'error': 'One or both items not found'}), 404
        
        if item1.collection_id != collection_id or item2.collection_id != collection_id:
            return jsonify({'error': 'Items do not belong to this collection'}), 400
        
        if item1_id == item2_id:
            return jsonify({'error': 'Cannot compare an item with itself'}), 400
        
        # Ensure consistent ordering (smaller ID first for display)
        if item1_id > item2_id:
            item1, item2 = item2, item1
            item1_id, item2_id = item2_id, item1_id
        
        return jsonify({
            'item1': {
                'id': item1.id,
                'name': item1.name,
                'media_link': item1.media_link
            },
            'item2': {
                'id': item2.id,
                'name': item2.name,
                'media_link': item2.media_link
            }
        })
    
    # Otherwise, get smart matchup using merge-sort-like approach
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

@app.route('/api/collections/<int:collection_id>', methods=['PUT', 'PATCH'])
def update_collection(collection_id):
    """Update collection properties like search_prefix."""
    collection = Collection.query.get_or_404(collection_id)
    data = request.json
    
    if 'name' in data:
        collection.name = data['name'].strip()
    if 'search_prefix' in data:
        collection.search_prefix = data['search_prefix'].strip() if data['search_prefix'] else None
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'collection': {
            'id': collection.id,
            'name': collection.name,
            'search_prefix': collection.search_prefix
        }
    })

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

@app.route('/api/items/<int:item_id>/auto-youtube', methods=['POST'])
def auto_fill_youtube(item_id):
    """
    Auto-fill YouTube link by searching for the item and getting first result.
    
    Supports two methods:
    1. YouTube Data API v3 (preferred, requires YOUTUBE_API_KEY env var)
    2. HTML scraping fallback (works without API key, less reliable)
    """
    item = Item.query.get_or_404(item_id)
    collection = item.collection
    
    # Build search query: prefix + item name
    search_query = item.name
    if collection.search_prefix:
        search_query = f"{collection.search_prefix} {item.name}"
    
    try:
        import requests
        import re
        import json as json_lib
        
        # Method 1: Try YouTube Data API v3 first (if API key is configured)
        youtube_api_key = os.environ.get('YOUTUBE_API_KEY')
        if youtube_api_key:
            api_url = 'https://www.googleapis.com/youtube/v3/search'
            params = {
                'part': 'snippet',
                'q': search_query,
                'type': 'video',
                'maxResults': 1,
                'key': youtube_api_key
            }
            
            response = requests.get(api_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('items') and len(data['items']) > 0:
                    video_id = data['items'][0]['id']['videoId']
                    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
                    
                    # Update item
                    item.media_link = normalize_youtube_url(youtube_url)
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
        
        # Method 2: Fallback - Try scraping YouTube search results
        # Note: YouTube's HTML structure changes frequently, so this may break
        try:
            from bs4 import BeautifulSoup
            
            search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(search_query)}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5'
            }
            
            response = requests.get(search_url, headers=headers, timeout=10)
            if response.status_code == 200:
                # Parse HTML to find first video link
                # Look for /watch?v=VIDEO_ID pattern in the page
                page_text = response.text
                # Look for /watch?v=VIDEO_ID pattern
                video_id_pattern = r'/watch\?v=([a-zA-Z0-9_-]{11})'
                matches = re.findall(video_id_pattern, page_text)
                if matches:
                    # Take the first unique video ID found
                    video_id = matches[0]
                    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
                    item.media_link = normalize_youtube_url(youtube_url)
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
                
                # Alternative: Try parsing JSON from ytInitialData
                soup = BeautifulSoup(response.text, 'html.parser')
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string and 'var ytInitialData' in script.string:
                        match = re.search(r'var ytInitialData = ({.*?});', script.string, re.DOTALL)
                        if match:
                            try:
                                data = json_lib.loads(match.group(1))
                                # Navigate through nested structure to find first video
                                contents = data.get('contents', {})
                                two_column = contents.get('twoColumnSearchResultsRenderer', {})
                                primary_contents = two_column.get('primaryContents', {})
                                section_list = primary_contents.get('sectionListRenderer', {})
                                contents_list = section_list.get('contents', [])
                                
                                for section in contents_list:
                                    item_section = section.get('itemSectionRenderer', {})
                                    items_list = item_section.get('contents', [])
                                    for video_item in items_list:
                                        video_renderer = video_item.get('videoRenderer', {})
                                        if video_renderer:
                                            video_id = video_renderer.get('videoId')
                                            if video_id:
                                                youtube_url = f"https://www.youtube.com/watch?v={video_id}"
                                                item.media_link = normalize_youtube_url(youtube_url)
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
                            except (json_lib.JSONDecodeError, KeyError, TypeError) as e:
                                # If JSON parsing fails, continue to next method
                                pass
        except Exception as scrape_error:
            # If scraping fails, log but don't fail the request yet
            print(f"Scraping fallback failed: {scrape_error}")
        
        return jsonify({
            'error': 'Could not find YouTube video. Please try setting YOUTUBE_API_KEY environment variable for better results, or manually search and add the link.'
        }), 400
        
    except Exception as e:
        return jsonify({'error': f'Error fetching YouTube result: {str(e)}'}), 500

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

@app.route('/api/items/<int:item_id>/votes', methods=['GET'])
def get_item_votes(item_id):
    """Get voting history for an item - wins, losses, and ties."""
    item = Item.query.get_or_404(item_id)
    
    # Get all comparisons involving this item
    comparisons_as_item1 = Comparison.query.filter_by(item1_id=item.id).all()
    comparisons_as_item2 = Comparison.query.filter_by(item2_id=item.id).all()
    
    wins = []
    losses = []
    ties = []
    
    # Process comparisons where item is item1
    for comp in comparisons_as_item1:
        other_item = db.session.get(Item, comp.item2_id)
        if not other_item:
            continue
        
        comparison_data = {
            'other_item_id': other_item.id,
            'other_item_name': other_item.name,
            'other_item_media_link': other_item.media_link,
            'comparison_id': comp.id
        }
        
        if comp.result == 'item1':
            wins.append(comparison_data)
        elif comp.result == 'item2':
            losses.append(comparison_data)
        elif comp.result == 'tie':
            ties.append(comparison_data)
    
    # Process comparisons where item is item2
    for comp in comparisons_as_item2:
        other_item = db.session.get(Item, comp.item1_id)
        if not other_item:
            continue
        
        comparison_data = {
            'other_item_id': other_item.id,
            'other_item_name': other_item.name,
            'other_item_media_link': other_item.media_link,
            'comparison_id': comp.id
        }
        
        if comp.result == 'item1':
            losses.append(comparison_data)
        elif comp.result == 'item2':
            wins.append(comparison_data)
        elif comp.result == 'tie':
            ties.append(comparison_data)
    
    return jsonify({
        'item': {
            'id': item.id,
            'name': item.name,
            'media_link': item.media_link,
            'points': item.points
        },
        'wins': wins,
        'losses': losses,
        'ties': ties
    })

@app.route('/api/items/<int:item_id>/votes', methods=['DELETE'])
def reset_item_votes(item_id):
    """Reset all votes for an item - remove all comparisons involving this item."""
    item = Item.query.get_or_404(item_id)
    collection_id = item.collection_id
    
    # Get all comparisons involving this item
    comparisons_as_item1 = Comparison.query.filter_by(item1_id=item.id).all()
    comparisons_as_item2 = Comparison.query.filter_by(item2_id=item.id).all()
    
    reset_count = 0
    
    # Reset points for comparisons where item is item1
    for comp in comparisons_as_item1:
        other_item = db.session.get(Item, comp.item2_id)
        if other_item:
            # Reverse point adjustments
            if comp.result == 'item1':
                item.points -= 1
                other_item.points += 1
            elif comp.result == 'item2':
                item.points += 1
                other_item.points -= 1
            # Ties don't affect points
        db.session.delete(comp)
        reset_count += 1
    
    # Reset points for comparisons where item is item2
    for comp in comparisons_as_item2:
        other_item = db.session.get(Item, comp.item1_id)
        if other_item:
            # Reverse point adjustments
            if comp.result == 'item1':
                item.points += 1
                other_item.points -= 1
            elif comp.result == 'item2':
                item.points -= 1
                other_item.points += 1
            # Ties don't affect points
        db.session.delete(comp)
        reset_count += 1
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'comparisons_reset': reset_count,
        'item': {
            'id': item.id,
            'name': item.name,
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
            'search_prefix': collection.search_prefix,
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
    collection = Collection(
        name=data['collection']['name'],
        search_prefix=data['collection'].get('search_prefix')
    )
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

# Smart matchup algorithm - prioritizes largest tied groups
def get_smart_matchup(collection):
    """
    Uses a smart approach to find the next comparison to make.
    Prioritizes comparisons within the largest subset of items with the same score.
    
    Selection criteria:
    1. Find the largest subset of items that have the same score
    2. If multiple subsets have the same size, prioritize the one with the highest score
    3. Select matchups from within that subset
    4. Within the selected subset, prefer items with fewer comparisons
    5. Randomize for better distribution
    """
    import random
    
    items = list(collection.items)
    comparisons = {frozenset({c.item1_id, c.item2_id}): c.result 
                   for c in collection.comparisons}
    
    if len(items) < 2:
        return None
    
    # Count comparisons per item
    item_comparison_counts = {}
    for item in items:
        item_comparison_counts[item.id] = sum(
            1 for c in comparisons.keys() if item.id in c
        )
    
    # Group items by score
    items_by_score = {}
    for item in items:
        score = item.points
        if score not in items_by_score:
            items_by_score[score] = []
        items_by_score[score].append(item)
    
    # Find the largest subset(s) of items with the same score
    max_group_size = max(len(group) for group in items_by_score.values())
    largest_groups = [(score, group) for score, group in items_by_score.items() 
                      if len(group) == max_group_size]
    
    # If multiple groups have the same size, prioritize the one with smallest absolute value
    # Tie-breaking: 0, then 1, -1, then 2, -2, then 3, -3, etc.
    # (smallest absolute value first, then positive over negative)
    def tie_break_key(score_group_pair):
        score = score_group_pair[0]
        abs_score = abs(score)
        # Return tuple: (absolute_value, is_negative)
        # This sorts: 0, 1, -1, 2, -2, 3, -3, ...
        return (abs_score, score < 0)
    
    largest_groups.sort(key=tie_break_key)
    target_score, target_group = largest_groups[0]
    
    # If the target group has fewer than 2 items, we can't create a matchup from it
    # This shouldn't happen if we're selecting correctly, but handle it gracefully
    if len(target_group) < 2:
        # Fall back to finding any possible matchup
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                item1, item2 = items[i], items[j]
                matchup_key = frozenset({item1.id, item2.id})
                if matchup_key not in comparisons:
                    return (item1, item2)
        return None
    
    # Get all possible matchups within the target group
    possible_matchups = []
    for i in range(len(target_group)):
        for j in range(i + 1, len(target_group)):
            item1, item2 = target_group[i], target_group[j]
            matchup_key = frozenset({item1.id, item2.id})
            
            # Skip if already compared
            if matchup_key in comparisons:
                continue
            
            # Count comparisons for each item
            item1_comparisons = item_comparison_counts.get(item1.id, 0)
            item2_comparisons = item_comparison_counts.get(item2.id, 0)
            total_comparisons = item1_comparisons + item2_comparisons
            max_comparisons = max(item1_comparisons, item2_comparisons)
            
            # Priority tuple: (max_comparisons, total_comparisons, random)
            # Lower values = higher priority
            random_tiebreaker = random.random()
            
            priority_tuple = (
                max_comparisons,   # Primary: max comparisons (prefer items with fewer)
                total_comparisons, # Secondary: total comparisons
                random_tiebreaker  # Tertiary: random for distribution
            )
            
            possible_matchups.append((priority_tuple, (item1, item2)))
    
    # If no matchups available in target group, look for any unmatched pair
    if not possible_matchups:
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                item1, item2 = items[i], items[j]
                matchup_key = frozenset({item1.id, item2.id})
                if matchup_key not in comparisons:
                    return (item1, item2)
        return None
    
    # Sort by priority tuple (lower is better)
    possible_matchups.sort(key=lambda x: x[0])
    
    # Group by primary criteria (max_comparisons)
    best_max_comparisons = possible_matchups[0][0][0]
    best_matchups = [m for m in possible_matchups if m[0][0] == best_max_comparisons]
    
    # If multiple matchups with same max_comparisons, filter by total_comparisons
    if len(best_matchups) > 1:
        best_matchups.sort(key=lambda x: x[0][1])  # Sort by total_comparisons
        best_total_comparisons = best_matchups[0][0][1]
        best_matchups = [m for m in best_matchups if m[0][1] == best_total_comparisons]
    
    # If still multiple, use random selection from the best group
    selected = random.choice(best_matchups)
    
    # Return the matchup (item1, item2)
    return selected[1]

# Initialize database (only if not in testing mode)
# This prevents tests from accidentally creating/modifying production database
if not os.environ.get('TESTING') and not app.config.get('TESTING'):
    with app.app_context():
        db.create_all()
        
        # Migration: Add columns if they don't exist (for existing databases)
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            
            # Migration: Add media_link column if it doesn't exist
            item_columns = [col['name'] for col in inspector.get_columns('item')]
            if 'media_link' not in item_columns:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE item ADD COLUMN media_link VARCHAR(1000)'))
                    conn.commit()
                print("✓ Added media_link column to existing database")
            
            # Migration: Add search_prefix column if it doesn't exist
            collection_columns = [col['name'] for col in inspector.get_columns('collection')]
            if 'search_prefix' not in collection_columns:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE collection ADD COLUMN search_prefix VARCHAR(200)'))
                    conn.commit()
                print("✓ Added search_prefix column to existing database")
        except Exception as e:
            # If migration fails, it's likely a new database or the column already exists
            pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

