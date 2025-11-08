"""Tests for collection update endpoints."""
import pytest
from app import db, Collection

def test_update_collection_name(client, sample_collection):
    """Test updating collection name."""
    response = client.put(f'/api/collections/{sample_collection}',
        json={'name': 'Updated Collection Name'},
        content_type='application/json'
    )
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['success'] == True
    assert data['collection']['name'] == 'Updated Collection Name'
    assert data['collection']['id'] == sample_collection
    
    # Verify update persisted
    get_response = client.get(f'/api/collections/{sample_collection}')
    collection = get_response.get_json()
    assert collection['name'] == 'Updated Collection Name'

def test_update_collection_search_prefix(client, sample_collection):
    """Test updating collection search prefix."""
    response = client.patch(f'/api/collections/{sample_collection}',
        json={'search_prefix': 'test prefix'},
        content_type='application/json'
    )
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['success'] == True
    assert data['collection']['search_prefix'] == 'test prefix'
    
    # Verify update persisted
    get_response = client.get(f'/api/collections/{sample_collection}')
    collection = get_response.get_json()
    assert collection['search_prefix'] == 'test prefix'

def test_update_collection_both_fields(client, sample_collection):
    """Test updating both name and search_prefix."""
    response = client.put(f'/api/collections/{sample_collection}',
        json={
            'name': 'New Name',
            'search_prefix': 'New Prefix'
        },
        content_type='application/json'
    )
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['collection']['name'] == 'New Name'
    assert data['collection']['search_prefix'] == 'New Prefix'

def test_update_collection_clear_search_prefix(client, sample_collection):
    """Test clearing search prefix by setting to empty string."""
    # First set a prefix
    client.patch(f'/api/collections/{sample_collection}',
        json={'search_prefix': 'original prefix'},
        content_type='application/json'
    )
    
    # Clear it
    response = client.patch(f'/api/collections/{sample_collection}',
        json={'search_prefix': ''},
        content_type='application/json'
    )
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['collection']['search_prefix'] is None
    
    # Verify update persisted
    get_response = client.get(f'/api/collections/{sample_collection}')
    collection = get_response.get_json()
    assert collection['search_prefix'] is None

def test_update_collection_not_found(client):
    """Test updating non-existent collection."""
    response = client.put('/api/collections/99999',
        json={'name': 'Test'},
        content_type='application/json'
    )
    assert response.status_code == 404

def test_update_collection_name_trimmed(client, sample_collection):
    """Test that collection name is trimmed."""
    response = client.put(f'/api/collections/{sample_collection}',
        json={'name': '  Trimmed Name  '},
        content_type='application/json'
    )
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['collection']['name'] == 'Trimmed Name'
