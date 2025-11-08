"""Tests for item update endpoints."""
import pytest
from app import db, Item

def test_update_item_name(client, sample_collection):
    """Test updating item name."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_id = items[0].id
        
        response = client.put(f'/api/items/{item_id}',
            json={'name': 'Updated Item Name'},
            content_type='application/json'
        )
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['success'] == True
        assert data['item']['name'] == 'Updated Item Name'
        assert data['item']['id'] == item_id
        
        # Verify update persisted
        item = db.session.get(Item, item_id)
        assert item.name == 'Updated Item Name'

def test_update_item_media_link(client, sample_collection):
    """Test updating item media link."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_id = items[0].id
        
        response = client.patch(f'/api/items/{item_id}',
            json={'media_link': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
            content_type='application/json'
        )
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['item']['media_link'] == 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        
        # Verify update persisted
        item = db.session.get(Item, item_id)
        assert item.media_link == 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'

def test_update_item_media_link_video_id(client, sample_collection):
    """Test updating item media link with just video ID (should normalize)."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_id = items[0].id
        
        response = client.patch(f'/api/items/{item_id}',
            json={'media_link': 'dQw4w9WgXcQ'},
            content_type='application/json'
        )
        assert response.status_code == 200
        
        data = response.get_json()
        # Should normalize to full URL
        assert data['item']['media_link'] == 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'

def test_update_item_clear_media_link(client, sample_collection):
    """Test clearing media link by setting to empty string."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_id = items[0].id
        
        # First set a media link
        client.patch(f'/api/items/{item_id}',
            json={'media_link': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
            content_type='application/json'
        )
        
        # Clear it
        response = client.patch(f'/api/items/{item_id}',
            json={'media_link': ''},
            content_type='application/json'
        )
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['item']['media_link'] is None
        
        # Verify update persisted
        item = db.session.get(Item, item_id)
        assert item.media_link is None

def test_update_item_both_fields(client, sample_collection):
    """Test updating both name and media_link."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_id = items[0].id
        
        response = client.put(f'/api/items/{item_id}',
            json={
                'name': 'New Item Name',
                'media_link': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
            },
            content_type='application/json'
        )
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['item']['name'] == 'New Item Name'
        assert data['item']['media_link'] == 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'

def test_update_item_not_found(client):
    """Test updating non-existent item."""
    response = client.put('/api/items/99999',
        json={'name': 'Test'},
        content_type='application/json'
    )
    assert response.status_code == 404

def test_update_item_name_trimmed(client, sample_collection):
    """Test that item name is trimmed."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_id = items[0].id
        
        response = client.put(f'/api/items/{item_id}',
            json={'name': '  Trimmed Name  '},
            content_type='application/json'
        )
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['item']['name'] == 'Trimmed Name'

def test_update_item_points_not_modifiable(client, sample_collection):
    """Test that points cannot be modified via update endpoint."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_id = items[0].id
        original_points = items[0].points
        
        # Try to update points (should be ignored)
        response = client.put(f'/api/items/{item_id}',
            json={'name': 'Test', 'points': 999},
            content_type='application/json'
        )
        assert response.status_code == 200
        
        # Points should remain unchanged
        item = db.session.get(Item, item_id)
        assert item.points == original_points
