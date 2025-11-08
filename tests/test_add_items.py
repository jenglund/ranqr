"""Tests for adding items to collection endpoint."""
import pytest
from app import db, Item

def test_add_items_to_collection(client, sample_collection):
    """Test adding items to an existing collection."""
    response = client.post(f'/api/collections/{sample_collection}/items',
        json={'items': 'New Item 1\nNew Item 2\nNew Item 3'},
        content_type='application/json'
    )
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['success'] == True
    assert data['added'] == 3
    
    # Verify items were added
    collection_response = client.get(f'/api/collections/{sample_collection}')
    collection = collection_response.get_json()
    assert len(collection['items']) == 7  # 4 original + 3 new
    
    item_names = [item['name'] for item in collection['items']]
    assert 'New Item 1' in item_names
    assert 'New Item 2' in item_names
    assert 'New Item 3' in item_names

def test_add_items_empty_string(client, sample_collection):
    """Test adding empty items string (should add nothing)."""
    response = client.post(f'/api/collections/{sample_collection}/items',
        json={'items': ''},
        content_type='application/json'
    )
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['added'] == 0
    
    # Verify no items were added
    collection_response = client.get(f'/api/collections/{sample_collection}')
    collection = collection_response.get_json()
    assert len(collection['items']) == 4  # Original 4 items

def test_add_items_with_whitespace(client, sample_collection):
    """Test that items with whitespace are trimmed."""
    response = client.post(f'/api/collections/{sample_collection}/items',
        json={'items': '  Item 1  \n  Item 2  \nItem 3'},
        content_type='application/json'
    )
    assert response.status_code == 200
    
    # Verify items were trimmed
    collection_response = client.get(f'/api/collections/{sample_collection}')
    collection = collection_response.get_json()
    
    item_names = [item['name'] for item in collection['items']]
    assert 'Item 1' in item_names
    assert 'Item 2' in item_names
    assert 'Item 3' in item_names
    assert '  Item 1  ' not in item_names  # Should be trimmed

def test_add_items_skips_empty_lines(client, sample_collection):
    """Test that empty lines are skipped."""
    response = client.post(f'/api/collections/{sample_collection}/items',
        json={'items': 'Item 1\n\nItem 2\n   \nItem 3'},
        content_type='application/json'
    )
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['added'] == 3  # Only non-empty lines
    
    # Verify only non-empty items were added
    collection_response = client.get(f'/api/collections/{sample_collection}')
    collection = collection_response.get_json()
    
    item_names = [item['name'] for item in collection['items']]
    assert 'Item 1' in item_names
    assert 'Item 2' in item_names
    assert 'Item 3' in item_names

def test_add_items_to_nonexistent_collection(client):
    """Test adding items to non-existent collection."""
    response = client.post('/api/collections/99999/items',
        json={'items': 'Test Item'},
        content_type='application/json'
    )
    assert response.status_code == 404

def test_add_items_single_item(client, sample_collection):
    """Test adding a single item."""
    response = client.post(f'/api/collections/{sample_collection}/items',
        json={'items': 'Single Item'},
        content_type='application/json'
    )
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['added'] == 1
    
    # Verify item was added
    collection_response = client.get(f'/api/collections/{sample_collection}')
    collection = collection_response.get_json()
    assert len(collection['items']) == 5  # 4 original + 1 new
    
    item_names = [item['name'] for item in collection['items']]
    assert 'Single Item' in item_names

def test_add_items_new_items_have_zero_points(client, sample_collection):
    """Test that newly added items start with 0 points."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Create some comparisons to give items points
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
    
    # Add new items
    response = client.post(f'/api/collections/{sample_collection}/items',
        json={'items': 'New Item'},
        content_type='application/json'
    )
    assert response.status_code == 200
    
    # Verify new item has 0 points
    collection_response = client.get(f'/api/collections/{sample_collection}')
    collection = collection_response.get_json()
    
    new_item = next(item for item in collection['items'] if item['name'] == 'New Item')
    assert new_item['points'] == 0
