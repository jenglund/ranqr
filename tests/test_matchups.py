"""Tests for matchup functionality and point system."""
import pytest
from app import db, Item, Comparison

def test_get_matchup_requires_two_items(client):
    """Test that getting a matchup requires at least 2 items."""
    # Create collection with 1 item
    response = client.post('/api/collections',
        json={'name': 'Single Item', 'items': 'Only One'},
        content_type='application/json'
    )
    collection_id = response.get_json()['id']
    
    response = client.get(f'/api/collections/{collection_id}/matchup')
    assert response.status_code == 400

def test_get_matchup(client, sample_collection):
    """Test getting the next matchup."""
    response = client.get(f'/api/collections/{sample_collection}/matchup')
    assert response.status_code == 200
    data = response.get_json()
    assert 'item1' in data
    assert 'item2' in data
    assert 'id' in data['item1']
    assert 'name' in data['item1']
    assert 'id' in data['item2']
    assert 'name' in data['item2']
    assert data['item1']['id'] != data['item2']['id']

def test_submit_matchup_result(client, sample_collection):
    """Test submitting a matchup result."""
    # Get a matchup
    matchup_response = client.get(f'/api/collections/{sample_collection}/matchup')
    matchup = matchup_response.get_json()
    
    item1_id = matchup['item1']['id']
    item2_id = matchup['item2']['id']
    
    # Submit result
    response = client.post(f'/api/collections/{sample_collection}/matchup',
        json={
            'item1_id': item1_id,
            'item2_id': item2_id,
            'winner': 'item1'
        },
        content_type='application/json'
    )
    assert response.status_code == 200
    
    # Verify points were updated
    collection_response = client.get(f'/api/collections/{sample_collection}')
    items = collection_response.get_json()['items']
    item1 = next(i for i in items if i['id'] == item1_id)
    item2 = next(i for i in items if i['id'] == item2_id)
    assert item1['points'] == 1
    assert item2['points'] == -1

def test_matchup_point_system(client, sample_collection):
    """Test the point system for multiple matchups."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Item 0 beats Item 1
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Item 1 beats Item 2
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Item 0 beats Item 2
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Check points
        collection_response = client.get(f'/api/collections/{sample_collection}')
        items_data = collection_response.get_json()['items']
        
        item0 = next(i for i in items_data if i['id'] == item_ids[0])
        item1 = next(i for i in items_data if i['id'] == item_ids[1])
        item2 = next(i for i in items_data if i['id'] == item_ids[2])
        
        assert item0['points'] == 2  # Beat 2 items
        assert item1['points'] == 0   # Beat 1, lost to 1
        assert item2['points'] == -2  # Lost to 2 items

def test_tie_matchup(client, sample_collection):
    """Test that ties don't affect points."""
    matchup_response = client.get(f'/api/collections/{sample_collection}/matchup')
    matchup = matchup_response.get_json()
    
    item1_id = matchup['item1']['id']
    item2_id = matchup['item2']['id']
    
    # Get initial points
    collection_response = client.get(f'/api/collections/{sample_collection}')
    items = collection_response.get_json()['items']
    initial_item1 = next(i for i in items if i['id'] == item1_id)
    initial_item2 = next(i for i in items if i['id'] == item2_id)
    initial_points1 = initial_item1['points']
    initial_points2 = initial_item2['points']
    
    # Submit tie
    client.post(f'/api/collections/{sample_collection}/matchup',
        json={'item1_id': item1_id, 'item2_id': item2_id, 'winner': 'tie'},
        content_type='application/json'
    )
    
    # Verify points didn't change
    collection_response = client.get(f'/api/collections/{sample_collection}')
    items = collection_response.get_json()['items']
    final_item1 = next(i for i in items if i['id'] == item1_id)
    final_item2 = next(i for i in items if i['id'] == item2_id)
    assert final_item1['points'] == initial_points1
    assert final_item2['points'] == initial_points2

def test_update_matchup_result(client, sample_collection):
    """Test updating an existing matchup result."""
    matchup_response = client.get(f'/api/collections/{sample_collection}/matchup')
    matchup = matchup_response.get_json()
    
    item1_id = matchup['item1']['id']
    item2_id = matchup['item2']['id']
    
    # First result: item1 wins
    client.post(f'/api/collections/{sample_collection}/matchup',
        json={'item1_id': item1_id, 'item2_id': item2_id, 'winner': 'item1'},
        content_type='application/json'
    )
    
    # Update: item2 wins (reversing the result)
    client.post(f'/api/collections/{sample_collection}/matchup',
        json={'item1_id': item1_id, 'item2_id': item2_id, 'winner': 'item2'},
        content_type='application/json'
    )
    
    # Verify points reflect the update
    collection_response = client.get(f'/api/collections/{sample_collection}')
    items = collection_response.get_json()['items']
    item1 = next(i for i in items if i['id'] == item1_id)
    item2 = next(i for i in items if i['id'] == item2_id)
    assert item1['points'] == -1
    assert item2['points'] == 1

def test_matchup_ordering_consistency(client, sample_collection):
    """Test that matchup ordering is handled consistently (smaller ID first)."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = sorted([item.id for item in items])
        
        # Submit with larger ID first
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[0], 'winner': 'item2'},
            content_type='application/json'
        )
        
        # Verify the result is stored correctly
        comparison = Comparison.query.filter_by(
            collection_id=sample_collection,
            item1_id=item_ids[0],  # Should be stored with smaller ID first
            item2_id=item_ids[1]
        ).first()
        assert comparison is not None
        assert comparison.result == 'item1'  # Winner should be adjusted

def test_all_comparisons_completed(client, sample_collection):
    """Test that matchup endpoint indicates when all comparisons are done."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Complete all possible comparisons (4 items = 6 comparisons)
        comparisons = [
            (item_ids[0], item_ids[1]),
            (item_ids[0], item_ids[2]),
            (item_ids[0], item_ids[3]),
            (item_ids[1], item_ids[2]),
            (item_ids[1], item_ids[3]),
            (item_ids[2], item_ids[3]),
        ]
        
        for item1_id, item2_id in comparisons:
            client.post(f'/api/collections/{sample_collection}/matchup',
                json={'item1_id': item1_id, 'item2_id': item2_id, 'winner': 'item1'},
                content_type='application/json'
            )
        
        # Try to get another matchup
        response = client.get(f'/api/collections/{sample_collection}/matchup')
        assert response.status_code == 200
        data = response.get_json()
        assert 'message' in data
        assert 'completed' in data['message'].lower()

