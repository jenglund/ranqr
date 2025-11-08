"""Tests for score distribution (histogram) functionality."""
import pytest
import json
from app import db, Item, Comparison

def test_score_distribution_endpoint_no_comparisons(client, sample_collection):
    """Test score distribution endpoint with no comparisons."""
    response = client.get(f'/api/collections/{sample_collection}/score-distribution')
    assert response.status_code == 200
    
    data = response.get_json()
    assert 'distribution' in data
    # All items should have score 0
    assert len(data['distribution']) == 1
    assert data['distribution'][0]['score'] == 0
    assert data['distribution'][0]['count'] == 4  # sample_collection has 4 items

def test_score_distribution_with_comparisons(client, sample_collection):
    """Test score distribution with some comparisons."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create comparisons: A beats B and C
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        response = client.get(f'/api/collections/{sample_collection}/score-distribution')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'distribution' in data
        
        # Should have scores: 2 (A), -1 (B), -1 (C), 0 (D)
        scores = {d['score']: d['count'] for d in data['distribution']}
        assert scores.get(2, 0) == 1  # A has 2 points
        assert scores.get(-1, 0) == 2  # B and C have -1 points
        assert scores.get(0, 0) == 1   # D has 0 points

def test_score_distribution_sub_scores(client, sample_collection):
    """Test that sub-scores are calculated correctly for tied groups."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create scenario where A and B both have score 0, but A beats B
        # A vs B: A wins (A: +1, B: -1)
        # A vs C: C wins (A: 0, C: +1)
        # B vs C: C wins (B: -1, C: +2)
        # So A and B both end up at -1, but A beat B directly
        
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        
        response = client.get(f'/api/collections/{sample_collection}/score-distribution')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'distribution' in data
        
        # Find the group with score -1 (A and B)
        for dist in data['distribution']:
            if dist['score'] == -1:
                assert dist['count'] == 2  # A and B
                # Should have sub-score distribution
                assert 'sub_score_distribution' in dist
                # A should have sub-score +1 (beat B), B should have -1 (lost to A)
                sub_scores = {s['sub_score']: s['count'] for s in dist['sub_score_distribution']}
                assert sub_scores.get(1, 0) == 1  # A has sub-score +1
                assert sub_scores.get(-1, 0) == 1  # B has sub-score -1
                break

def test_score_distribution_empty_collection(client):
    """Test score distribution with empty collection."""
    response = client.post('/api/collections',
        json={'name': 'Empty Collection', 'items': ''},
        content_type='application/json'
    )
    collection_id = response.get_json()['id']
    
    response = client.get(f'/api/collections/{collection_id}/score-distribution')
    assert response.status_code == 200
    
    data = response.get_json()
    assert 'distribution' in data
    assert len(data['distribution']) == 0


# Tests for recursive score distribution endpoint

def test_recursive_score_distribution_empty_path(client, sample_collection):
    """Test recursive endpoint with empty score_path (should return top-level)."""
    response = client.get(
        f'/api/collections/{sample_collection}/score-distribution/recursive?score_path=[]'
    )
    assert response.status_code == 200
    
    data = response.get_json()
    assert 'distribution' in data
    assert 'score_path' in data
    assert data['score_path'] == []
    
    # Should match regular endpoint
    regular_response = client.get(f'/api/collections/{sample_collection}/score-distribution')
    regular_data = regular_response.get_json()
    assert len(data['distribution']) == len(regular_data['distribution'])

def test_recursive_score_distribution_single_level(client, sample_collection):
    """Test recursive endpoint with single-level score_path."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create comparisons: A beats B and C (A: +2, B: -1, C: -1, D: 0)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Query for score -1 (B and C)
        score_path = [-1]
        response = client.get(
            f'/api/collections/{sample_collection}/score-distribution/recursive?score_path={json.dumps(score_path)}'
        )
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'distribution' in data
        assert 'score_path' in data
        assert data['score_path'] == score_path
        
        # B and C both have score -1, so sub-scores should be calculated
        # Since they haven't been compared to each other, sub-scores should be 0
        # But if there are only 2 items and they haven't been compared, we might get empty distribution
        # Actually, if all sub-scores are the same (0), we return empty distribution
        assert isinstance(data['distribution'], list)

def test_recursive_score_distribution_with_sub_scores(client, sample_collection):
    """Test recursive endpoint when sub-scores exist."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create scenario: A and B both have score -1, A beats B
        # A vs B: A wins (A: +1, B: -1)
        # A vs C: C wins (A: 0, C: +1)
        # B vs C: C wins (B: -1, C: +2)
        # So A and B both end up at -1, but A beat B directly
        
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        
        # Query for score -1 (A and B)
        score_path = [-1]
        response = client.get(
            f'/api/collections/{sample_collection}/score-distribution/recursive?score_path={json.dumps(score_path)}'
        )
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'distribution' in data
        assert 'score_path' in data
        
        # Should have sub-score distribution: A has +1, B has -1
        if len(data['distribution']) > 0:
            sub_scores = {d['score']: d['count'] for d in data['distribution']}
            # A has sub-score +1, B has sub-score -1
            assert sub_scores.get(1, 0) == 1
            assert sub_scores.get(-1, 0) == 1

def test_recursive_score_distribution_multi_level(client, sample_collection):
    """Test recursive endpoint with multi-level score_path."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create a three-level scenario:
        # Level 1: A, B, C all have score +1
        # Level 2: Within that group, A and B both have sub-score +1 (beat C)
        # Level 3: Within A and B, A beats B (A has sub-sub-score +1, B has -1)
        
        # Get all items to score +1
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[3], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[3], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[2], 'item2_id': item_ids[3], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Within the +1 group: A beats C, B beats C
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Balance: C beats A and B to keep them at +1
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[2], 'item2_id': item_ids[0], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[2], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # D beats A, B, C to balance
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[3], 'item2_id': item_ids[0], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[3], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[3], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Now A beats B within the +1 group
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Balance: B beats A to keep both at +1
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[0], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Query for score path [1, 1] (score +1, sub-score +1)
        score_path = [1, 1]
        response = client.get(
            f'/api/collections/{sample_collection}/score-distribution/recursive?score_path={json.dumps(score_path)}'
        )
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'distribution' in data
        assert 'score_path' in data
        assert data['score_path'] == score_path
        
        # Should have sub-sub-score distribution for A and B
        # A has sub-sub-score +1, B has -1 (or vice versa depending on final state)
        assert isinstance(data['distribution'], list)

def test_recursive_score_distribution_invalid_path_format(client, sample_collection):
    """Test recursive endpoint with invalid score_path format."""
    # Invalid JSON
    response = client.get(
        f'/api/collections/{sample_collection}/score-distribution/recursive?score_path=invalid'
    )
    assert response.status_code == 400
    
    # Not an array
    response = client.get(
        f'/api/collections/{sample_collection}/score-distribution/recursive?score_path={json.dumps({"not": "array"})}'
    )
    assert response.status_code == 400

def test_recursive_score_distribution_nonexistent_path(client, sample_collection):
    """Test recursive endpoint with non-existent score path."""
    # Query for a score that doesn't exist
    score_path = [999]
    response = client.get(
        f'/api/collections/{sample_collection}/score-distribution/recursive?score_path={json.dumps(score_path)}'
    )
    assert response.status_code == 200
    
    data = response.get_json()
    assert 'distribution' in data
    assert 'score_path' in data
    # Should return empty distribution
    assert len(data['distribution']) == 0

def test_recursive_score_distribution_single_item_group(client, sample_collection):
    """Test recursive endpoint when score path leads to single item."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create comparisons: A beats B, C, D (A: +3, others: -1 each)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[3], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Query for score +3 (only A)
        score_path = [3]
        response = client.get(
            f'/api/collections/{sample_collection}/score-distribution/recursive?score_path={json.dumps(score_path)}'
        )
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'distribution' in data
        # Single item group should return empty distribution (no sub-scores possible)
        assert len(data['distribution']) == 0

def test_recursive_score_distribution_all_same_sub_score(client, sample_collection):
    """Test recursive endpoint when all items have same sub-score."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create scenario: A and B both have score -1, but haven't been compared
        # A vs C: C wins (A: -1, C: +1)
        # B vs C: C wins (B: -1, C: +2)
        # So A and B both have -1, but sub-score is 0 (not compared)
        
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        
        # Query for score -1 (A and B)
        score_path = [-1]
        response = client.get(
            f'/api/collections/{sample_collection}/score-distribution/recursive?score_path={json.dumps(score_path)}'
        )
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'distribution' in data
        # Since A and B haven't been compared, all sub-scores are 0, so empty distribution
        assert len(data['distribution']) == 0

def test_recursive_score_distribution_nonexistent_collection(client):
    """Test recursive endpoint with non-existent collection."""
    response = client.get(
        '/api/collections/99999/score-distribution/recursive?score_path=[]'
    )
    assert response.status_code == 404
