"""Tests for matchup selection algorithm - prioritizing largest tied groups."""

def test_selects_from_largest_tied_group(client, sample_collection):
    """Test that matchup selection prioritizes the largest group of items with same score."""
    with client.application.app_context():
        from app import Item
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # sample_collection has 4 items (A, B, C, D)
        # Create scenario:
        # - 3 items with score -1 (A, B, C)
        # - 1 item with score +3 (D)
        # Algorithm should select from the group of 3 (score -1)
        
        # Set up: D beats A, B, C (D: +3, A/B/C: -1 each)
        for other_id in item_ids[:3]:
            client.post(f'/api/collections/{sample_collection}/matchup',
                json={'item1_id': item_ids[3], 'item2_id': other_id, 'winner': 'item1'},
                content_type='application/json'
            )
        
        # Now: A, B, C all have score -1
        # D has score +3
        # Largest group is A, B, C (size 3) vs D (size 1)
        # Should select from A, B, C
        
        matchup_response = client.get(f'/api/collections/{sample_collection}/matchup')
        matchup = matchup_response.get_json()
        
        matchup_ids = {matchup['item1']['id'], matchup['item2']['id']}
        
        # Both items should be from the largest group (A, B, C)
        assert all(item_id in item_ids[:3] for item_id in matchup_ids), \
            f"Expected matchup from items {item_ids[:3]}, got {matchup_ids}"


def test_selects_smallest_absolute_value_when_groups_same_size(client, sample_collection):
    """Test that when multiple groups have same size, prioritize smallest absolute value."""
    with client.application.app_context():
        from app import Item
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # sample_collection has 4 items (A, B, C, D)
        # Create scenario:
        # - 2 items with score -2 (A, B)
        # - 2 items with score +2 (C, D)
        # Both groups have size 2, both have abs value 2
        # Should prioritize positive (+2) over negative (-2)
        
        # Set up: C beats A, B (C: +2, A/B: -1 each)
        for other_id in [item_ids[0], item_ids[1]]:
            client.post(f'/api/collections/{sample_collection}/matchup',
                json={'item1_id': item_ids[2], 'item2_id': other_id, 'winner': 'item1'},
                content_type='application/json'
            )
        
        # D beats A, B (D: +2, A/B: -2 each, C: +2)
        for other_id in [item_ids[0], item_ids[1]]:
            client.post(f'/api/collections/{sample_collection}/matchup',
                json={'item1_id': item_ids[3], 'item2_id': other_id, 'winner': 'item1'},
                content_type='application/json'
            )
        
        # Now: A, B both have score -2
        # C, D both have score +2
        # Both groups have size 2, abs values are equal (2), so should prioritize +2 over -2
        
        matchup_response = client.get(f'/api/collections/{sample_collection}/matchup')
        matchup = matchup_response.get_json()
        
        matchup_ids = {matchup['item1']['id'], matchup['item2']['id']}
        
        # Both items should be from the group with positive score (C, D)
        assert all(item_id in item_ids[2:4] for item_id in matchup_ids), \
            f"Expected matchup from items {item_ids[2:4]} (score +2), got {matchup_ids}"


def test_selects_zero_over_positive_when_groups_same_size(client):
    """Test that score 0 is prioritized over positive scores when groups have same size."""
    # Create a collection with 5 items to have more flexibility
    response = client.post('/api/collections',
        json={'name': 'Zero Priority Test', 'items': 'A\nB\nC\nD\nE'},
        content_type='application/json'
    )
    collection_id = response.get_json()['id']
    
    with client.application.app_context():
        from app import Item
        items = Item.query.filter_by(collection_id=collection_id).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create scenario:
        # - 2 items with score 0 (A, B) - smallest absolute value
        # - 2 items with score +1 (C, D) - larger absolute value
        # Both groups have size 2, should prioritize score 0
        
        # Set up: C beats E (C: +1, E: -1)
        client.post(f'/api/collections/{collection_id}/matchup',
            json={'item1_id': item_ids[2], 'item2_id': item_ids[4], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # D beats E (D: +1, E: -2, C: +1)
        client.post(f'/api/collections/{collection_id}/matchup',
            json={'item1_id': item_ids[3], 'item2_id': item_ids[4], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Now: A, B both have score 0 (no comparisons yet)
        # C, D both have score +1
        # E has score -2
        # Largest groups: A, B (score 0, size 2) and C, D (score +1, size 2)
        # Should prioritize A, B (score 0, smaller absolute value)
        
        matchup_response = client.get(f'/api/collections/{collection_id}/matchup')
        matchup = matchup_response.get_json()
        
        matchup_ids = {matchup['item1']['id'], matchup['item2']['id']}
        
        # Both items should be from the group with score 0 (A, B)
        assert all(item_id in item_ids[:2] for item_id in matchup_ids), \
            f"Expected matchup from items {item_ids[:2]} (score 0), got {matchup_ids}"


def test_selects_smaller_absolute_value_over_larger(client):
    """Test that smaller absolute values are prioritized over larger ones."""
    # Create a collection with 5 items
    response = client.post('/api/collections',
        json={'name': 'Abs Value Test', 'items': 'A\nB\nC\nD\nE'},
        content_type='application/json'
    )
    collection_id = response.get_json()['id']
    
    with client.application.app_context():
        from app import Item
        items = Item.query.filter_by(collection_id=collection_id).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create scenario:
        # - 2 items with score +1 (A, B) - absolute value 1
        # - 2 items with score +3 (C, D) - absolute value 3
        # Both groups have size 2, should prioritize +1 (smaller absolute value)
        
        # Set up: A beats E (A: +1, E: -1)
        client.post(f'/api/collections/{collection_id}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[4], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # B beats E (B: +1, E: -2, A: +1)
        client.post(f'/api/collections/{collection_id}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[4], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # C beats A, B, E (C: +3, A/B: 0 each, E: -3)
        for other_id in [item_ids[0], item_ids[1], item_ids[4]]:
            client.post(f'/api/collections/{collection_id}/matchup',
                json={'item1_id': item_ids[2], 'item2_id': other_id, 'winner': 'item1'},
                content_type='application/json'
            )
        
        # D beats A, B, E (D: +3, A/B: -1 each, E: -4, C: +3)
        for other_id in [item_ids[0], item_ids[1], item_ids[4]]:
            client.post(f'/api/collections/{collection_id}/matchup',
                json={'item1_id': item_ids[3], 'item2_id': other_id, 'winner': 'item1'},
                content_type='application/json'
            )
        
        # Now: A, B both have score -1 (after being beaten by C and D)
        # Wait, let me recalculate:
        # After A beats E: A: +1, E: -1
        # After B beats E: B: +1, E: -2, A: +1
        # After C beats A, B, E: C: +3, A: 0, B: 0, E: -3
        # After D beats A, B, E: D: +3, A: -1, B: -1, E: -4, C: +3
        
        # Now: A, B both have score -1, C, D both have score +3
        # Groups: A, B (score -1, size 2), C, D (score +3, size 2)
        # Both have size 2, abs values: 1 vs 3, should prioritize -1 (smaller abs value)
        
        matchup_response = client.get(f'/api/collections/{collection_id}/matchup')
        matchup = matchup_response.get_json()
        
        matchup_ids = {matchup['item1']['id'], matchup['item2']['id']}
        
        # Both items should be from the group with smaller absolute value (A, B with score -1)
        assert all(item_id in item_ids[:2] for item_id in matchup_ids), \
            f"Expected matchup from items {item_ids[:2]} (score -1, abs value 1), got {matchup_ids}"


def test_selects_from_largest_group_after_some_comparisons(client, sample_collection):
    """Test that algorithm still selects from largest group even after some comparisons."""
    with client.application.app_context():
        from app import Item
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # sample_collection has 4 items (A, B, C, D)
        # Create scenario:
        # - 3 items with score -1 (A, B, C) - largest group, size 3
        # - 1 item with score +3 (D) - size 1
        
        # Set up: D beats A, B, C (D: +3, A/B/C: -1 each)
        for other_id in item_ids[:3]:
            client.post(f'/api/collections/{sample_collection}/matchup',
                json={'item1_id': item_ids[3], 'item2_id': other_id, 'winner': 'item1'},
                content_type='application/json'
            )
        
        # Verify it selects from A, B, C before any comparisons within the group
        matchup_response = client.get(f'/api/collections/{sample_collection}/matchup')
        matchup = matchup_response.get_json()
        
        matchup_ids = {matchup['item1']['id'], matchup['item2']['id']}
        
        # Both items should be from the largest group (A, B, C)
        assert all(item_id in item_ids[:3] for item_id in matchup_ids), \
            f"Expected matchup from largest group {item_ids[:3]}, got {matchup_ids}"


def test_all_items_same_score_selects_any(client, sample_collection):
    """Test that when all items have the same score, algorithm can select any matchup."""
    with client.application.app_context():
        from app import Item
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # All items start at score 0
        # Should be able to select any matchup
        
        matchup_response = client.get(f'/api/collections/{sample_collection}/matchup')
        matchup = matchup_response.get_json()
        
        matchup_ids = {matchup['item1']['id'], matchup['item2']['id']}
        
        # Should be a valid matchup (both items in the collection)
        assert all(item_id in item_ids for item_id in matchup_ids)
        assert len(matchup_ids) == 2
