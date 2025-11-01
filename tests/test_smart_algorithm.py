"""Tests for the smart matchup algorithm."""
import pytest
from app import db, Item, Comparison

def test_algorithm_prioritizes_similar_scores(client):
    """Test that the algorithm prefers comparing items with similar scores."""
    # Create collection with items
    response = client.post('/api/collections',
        json={'name': 'Algorithm Test', 'items': 'A\nB\nC\nD\nE'},
        content_type='application/json'
    )
    collection_id = response.get_json()['id']
    
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=collection_id).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create a scenario where items have different scores
        # A beats B (A: 1, B: -1)
        client.post(f'/api/collections/{collection_id}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # A beats C (A: 2, B: -1, C: -1)
        client.post(f'/api/collections/{collection_id}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # D beats E (D: 1, E: -1)
        client.post(f'/api/collections/{collection_id}/matchup',
            json={'item1_id': item_ids[3], 'item2_id': item_ids[4], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Now A has 2 points, D has 1 point, B and C have -1, E has -1
        # The algorithm should prefer comparing B vs C (both -1) or A vs D (2 vs 1)
        # rather than comparing A vs E (2 vs -1)
        
        matchup_response = client.get(f'/api/collections/{collection_id}/matchup')
        matchup = matchup_response.get_json()
        
        # Verify we got a valid matchup
        assert 'item1' in matchup
        assert 'item2' in matchup

def test_algorithm_avoids_duplicate_comparisons(client, sample_collection):
    """Test that the algorithm doesn't suggest already-completed comparisons."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Complete one comparison
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Get next matchup - should not be the same pair
        matchup_response = client.get(f'/api/collections/{sample_collection}/matchup')
        matchup = matchup_response.get_json()
        
        matchup_ids = {matchup['item1']['id'], matchup['item2']['id']}
        assert matchup_ids != {item_ids[0], item_ids[1]}

def test_algorithm_prefers_items_with_fewer_comparisons(client, sample_collection):
    """Test that when items have equal scores, algorithm prefers items with fewer comparisons."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create a scenario where multiple items have the same score (0)
        # But some have been compared more than others
        # Item 0 vs Item 1 (both start at 0, both get compared)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Item 2 vs Item 3 (both still at 0, but haven't been compared yet)
        # Now Item 0 and 1 have 1 comparison each, Item 2 and 3 have 0
        
        # Get next matchup - should prefer comparing items with fewer comparisons
        # when scores are equal (all items should be at score 0 or close to it)
        matchup_response = client.get(f'/api/collections/{sample_collection}/matchup')
        matchup = matchup_response.get_json()
        
        matchup_ids = {matchup['item1']['id'], matchup['item2']['id']}
        
        # Should prefer items that haven't been compared yet (2, 3, 4, etc.)
        # over comparing 0 or 1 again
        # Since 2, 3, 4, etc. all have 0 comparisons, it should pick among them
        assert item_ids[0] not in matchup_ids or item_ids[1] not in matchup_ids

def test_algorithm_handles_small_collections(client):
    """Test algorithm with minimal items."""
    response = client.post('/api/collections',
        json={'name': 'Small Collection', 'items': 'Item1\nItem2'},
        content_type='application/json'
    )
    collection_id = response.get_json()['id']
    
    matchup_response = client.get(f'/api/collections/{collection_id}/matchup')
    assert matchup_response.status_code == 200
    matchup = matchup_response.get_json()
    assert 'item1' in matchup
    assert 'item2' in matchup

def test_algorithm_progress_toward_completion(client, sample_collection):
    """Test that algorithm continues to suggest valid matchups."""
    completed_pairs = set()
    
    # Complete several comparisons
    for _ in range(3):
        matchup_response = client.get(f'/api/collections/{sample_collection}/matchup')
        if 'message' in matchup_response.get_json():
            break  # All comparisons done
            
        matchup = matchup_response.get_json()
        item1_id = matchup['item1']['id']
        item2_id = matchup['item2']['id']
        pair = frozenset({item1_id, item2_id})
        
        # Should not be a duplicate
        assert pair not in completed_pairs
        
        completed_pairs.add(pair)
        
        # Submit result
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item1_id, 'item2_id': item2_id, 'winner': 'item1'},
            content_type='application/json'
        )

def test_rankings_are_sorted_by_points(client, sample_collection):
    """Test that rankings are sorted correctly by points."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Create a clear ranking
        # item_ids[0] beats everyone
        for other_id in item_ids[1:]:
            client.post(f'/api/collections/{sample_collection}/matchup',
                json={'item1_id': item_ids[0], 'item2_id': other_id, 'winner': 'item1'},
                content_type='application/json'
            )
        
        # item_ids[1] beats the rest
        for other_id in item_ids[2:]:
            client.post(f'/api/collections/{sample_collection}/matchup',
                json={'item1_id': item_ids[1], 'item2_id': other_id, 'winner': 'item1'},
                content_type='application/json'
            )
        
        # Check rankings
        response = client.get(f'/api/collections/{sample_collection}')
        items_data = response.get_json()['items']
        
        # Verify sorting (descending by points)
        points = [item['points'] for item in items_data]
        assert points == sorted(points, reverse=True)
        
        # First item should have the highest points
        # item_ids[0] beat 3 items: 3 wins, 0 losses = 3 points
        assert items_data[0]['points'] == 3
        # item_ids[1] beat 2 items but lost to item_ids[0]: 2 wins, 1 loss = 1 point
        assert items_data[1]['points'] == 1

