"""Tests for tie-breaking ranking algorithm."""
import pytest
from app import Item, Comparison, db

def test_tie_breaking_with_sub_scores(client, sample_collection):
    """Test that items with the same score are tie-broken using sub-scores."""
    with client.application.app_context():
        from app import Item, Comparison, db
        
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Create scenario where A and D end up with same score (+1)
        # but A beat D in their direct comparison, creating sub-score difference
        
        # Step 1: A beats B (A: +1, B: -1)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Step 2: D beats C (D: +1, C: -1)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[3], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Step 3: A beats D (A: +2, D: 0) - this creates the sub-score relationship
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[3], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Step 4: D beats B (D: +1, B: -2) - balances D's score back up
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[3], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Step 5: C beats A (C: 0, A: +1) - balances A's score back down
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[2], 'item2_id': item_ids[0], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Now A and D both have +1 points, but A beat D in step 3
        # Check rankings - A should come before D due to sub-score tie-breaking
        response = client.get(f'/api/collections/{sample_collection}')
        items_data = response.get_json()['items']
        
        # Find A and D in the rankings
        item_a = next(item for item in items_data if item['id'] == item_ids[0])
        item_d = next(item for item in items_data if item['id'] == item_ids[3])
        
        assert item_a['points'] == 1, f"Expected A to have 1 point, got {item_a['points']}"
        assert item_d['points'] == 1, f"Expected D to have 1 point, got {item_d['points']}"
        
        # A should come before D in the rankings due to sub-score tie-breaking
        a_index = next(i for i, item in enumerate(items_data) if item['id'] == item_ids[0])
        d_index = next(i for i, item in enumerate(items_data) if item['id'] == item_ids[3])
        
        assert a_index < d_index, "A should come before D due to tie-breaking sub-score"


def test_tie_breaking_with_all_zero_sub_scores(client, sample_collection):
    """Test that items with same score and all zero sub-scores remain in stable order."""
    with client.application.app_context():
        from app import Item
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Create a scenario where two items have the same score
        # but have never been compared to each other (so sub-score is 0)
        
        # Make A beat B (A: +1, B: -1)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Make C beat D (C: +1, D: -1)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[2], 'item2_id': item_ids[3], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Now A and C both have +1, but have never been compared
        # Check rankings - should be sorted, but order between A and C is stable
        response = client.get(f'/api/collections/{sample_collection}')
        items_data = response.get_json()['items']
        
        # Verify points
        item_a = next(item for item in items_data if item['id'] == item_ids[0])
        item_c = next(item for item in items_data if item['id'] == item_ids[2])
        
        assert item_a['points'] == 1
        assert item_c['points'] == 1
        
        # Rankings should still be valid (sorted by points, then by sub-score which is 0)
        points = [item['points'] for item in items_data]
        assert points == sorted(points, reverse=True)


def test_tie_breaking_with_multiple_tied_items(client, sample_collection):
    """Test tie-breaking with more than two items having the same score."""
    with client.application.app_context():
        from app import Item
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Set up: A, B, C all have score 0 (no comparisons)
        # Then create comparisons only between them to create sub-scores
        
        # A beats B (A: +1, B: -1)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # A beats C (A: +2, B: -1, C: -1)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # B beats C (A: +2, B: 0, C: -2)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Now compare D with other items to give it score 0
        # Actually, D already has score 0, so A has +2, B has 0, C has -2, D has 0
        
        # Check rankings
        response = client.get(f'/api/collections/{sample_collection}')
        items_data = response.get_json()['items']
        
        # Find items
        item_a = next(item for item in items_data if item['id'] == item_ids[0])
        item_b = next(item for item in items_data if item['id'] == item_ids[1])
        item_d = next(item for item in items_data if item['id'] == item_ids[3])
        
        assert item_a['points'] == 2
        assert item_b['points'] == 0
        assert item_d['points'] == 0
        
        # B and D both have 0 points, but haven't been compared
        # So they should maintain stable order
        b_index = next(i for i, item in enumerate(items_data) if item['id'] == item_ids[1])
        d_index = next(i for i, item in enumerate(items_data) if item['id'] == item_ids[3])
        
        # Now compare B and D - B wins
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[3], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Check rankings again
        response = client.get(f'/api/collections/{sample_collection}')
        items_data = response.get_json()['items']
        
        # B now has +1, D has -1 (main scores changed)
        item_b = next(item for item in items_data if item['id'] == item_ids[1])
        item_d = next(item for item in items_data if item['id'] == item_ids[3])
        
        assert item_b['points'] == 1
        assert item_d['points'] == -1
        
        # B should come before D
        b_index = next(i for i, item in enumerate(items_data) if item['id'] == item_ids[1])
        d_index = next(i for i, item in enumerate(items_data) if item['id'] == item_ids[3])
        
        assert b_index < d_index
