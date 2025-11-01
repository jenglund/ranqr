"""Tests for collection management."""
import pytest

def test_create_collection(client):
    """Test creating a new collection."""
    response = client.post('/api/collections',
        json={
            'name': 'My Test Collection',
            'items': 'Item 1\nItem 2\nItem 3'
        },
        content_type='application/json'
    )
    
    assert response.status_code == 201
    data = response.get_json()
    assert 'id' in data
    assert data['name'] == 'My Test Collection'

def test_get_collections(client, sample_collection):
    """Test retrieving all collections."""
    # Create another collection
    client.post('/api/collections',
        json={'name': 'Second Collection', 'items': 'One\nTwo'},
        content_type='application/json'
    )
    
    response = client.get('/api/collections')
    assert response.status_code == 200
    collections = response.get_json()
    assert len(collections) == 2
    assert any(c['name'] == 'Test Collection' for c in collections)
    assert any(c['name'] == 'Second Collection' for c in collections)

def test_get_collection(client, sample_collection):
    """Test retrieving a specific collection."""
    response = client.get(f'/api/collections/{sample_collection}')
    assert response.status_code == 200
    data = response.get_json()
    assert data['id'] == sample_collection
    assert data['name'] == 'Test Collection'
    assert len(data['items']) == 4
    assert data['items'][0]['name'] == 'Apple'
    assert data['items'][1]['name'] == 'Banana'

def test_get_collection_not_found(client):
    """Test retrieving a non-existent collection."""
    response = client.get('/api/collections/999')
    assert response.status_code == 404

def test_delete_collection(client, sample_collection):
    """Test deleting a collection."""
    response = client.delete(f'/api/collections/{sample_collection}')
    assert response.status_code == 200
    
    # Verify it's deleted
    response = client.get(f'/api/collections/{sample_collection}')
    assert response.status_code == 404

def test_create_collection_with_empty_items(client):
    """Test creating a collection with no items."""
    response = client.post('/api/collections',
        json={'name': 'Empty Collection', 'items': ''},
        content_type='application/json'
    )
    assert response.status_code == 201
    
    response = client.get(f'/api/collections/{response.get_json()["id"]}')
    data = response.get_json()
    assert len(data['items']) == 0

def test_items_are_trimmed(client):
    """Test that items with extra whitespace are trimmed."""
    response = client.post('/api/collections',
        json={
            'name': 'Whitespace Test',
            'items': '  Item 1  \n  Item 2  \nItem 3'
        },
        content_type='application/json'
    )
    collection_id = response.get_json()['id']
    
    response = client.get(f'/api/collections/{collection_id}')
    items = response.get_json()['items']
    assert items[0]['name'] == 'Item 1'
    assert items[1]['name'] == 'Item 2'
    assert items[2]['name'] == 'Item 3'

