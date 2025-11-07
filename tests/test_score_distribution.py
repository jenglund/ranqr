"""Tests for score distribution (histogram) functionality."""
import pytest
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
