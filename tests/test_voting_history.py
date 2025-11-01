"""Tests for voting history and vote change functionality."""
import pytest
from app import db, Item, Comparison

def test_get_item_votes_empty(client, sample_collection):
    """Test getting votes for an item with no comparisons."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_id = items[0].id
        
        response = client.get(f'/api/items/{item_id}/votes')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['item']['id'] == item_id
        assert len(data['wins']) == 0
        assert len(data['losses']) == 0
        assert len(data['ties']) == 0

def test_get_item_votes_with_comparisons(client, sample_collection):
    """Test getting votes for an item with wins, losses, and ties."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Item 0 beats Item 1
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Item 2 beats Item 0
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        
        # Item 0 ties with Item 3
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[3], 'winner': 'tie'},
            content_type='application/json'
        )
        
        # Get votes for item 0
        response = client.get(f'/api/items/{item_ids[0]}/votes')
        assert response.status_code == 200
        
        data = response.get_json()
        assert len(data['wins']) == 1
        assert len(data['losses']) == 1
        assert len(data['ties']) == 1
        
        assert data['wins'][0]['other_item_id'] == item_ids[1]
        assert data['losses'][0]['other_item_id'] == item_ids[2]
        assert data['ties'][0]['other_item_id'] == item_ids[3]

def test_get_item_votes_as_item2(client, sample_collection):
    """Test getting votes when item appears as item2 in comparisons."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Item 1 beats Item 0 (item 0 is item2)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item2'},
            content_type='application/json'
        )
        
        # Get votes for item 1
        response = client.get(f'/api/items/{item_ids[1]}/votes')
        assert response.status_code == 200
        
        data = response.get_json()
        assert len(data['wins']) == 1
        assert data['wins'][0]['other_item_id'] == item_ids[0]

def test_reset_item_votes(client, sample_collection):
    """Test resetting all votes for an item."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Create several comparisons involving item 0
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[3], 'winner': 'item2'},  # Item 0 vs Item 3, Item 3 wins
            content_type='application/json'
        )
        
        # Get initial points after comparisons
        # Item 0: beat 1 (+1), beat 2 (+1), lost to 3 (-1) = +1 total
        # Item 1: lost to 0 (-1) = -1 total
        # Item 2: lost to 0 (-1) = -1 total  
        # Item 3: beat 0 (+1) = +1 total
        
        initial_item0 = db.session.get(Item, item_ids[0])
        initial_item1 = db.session.get(Item, item_ids[1])
        initial_item2 = db.session.get(Item, item_ids[2])
        initial_item3 = db.session.get(Item, item_ids[3])
        initial_points0 = initial_item0.points  # Should be +1
        initial_points1 = initial_item1.points  # Should be -1
        initial_points2 = initial_item2.points  # Should be -1
        initial_points3 = initial_item3.points  # Should be +1
        
        # Reset votes for item 0
        response = client.delete(f'/api/items/{item_ids[0]}/votes')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['success'] == True
        assert data['comparisons_reset'] == 3
        
        # Verify points were adjusted
        final_item0 = db.session.get(Item, item_ids[0])
        final_item1 = db.session.get(Item, item_ids[1])
        final_item2 = db.session.get(Item, item_ids[2])
        final_item3 = db.session.get(Item, item_ids[3])
        
        # Item 0 should have 0 points (all comparisons removed)
        assert final_item0.points == 0
        
        # Other items should have points adjusted back to 0
        # Item 1 lost to item 0, so it should gain back the point: -1 + 1 = 0
        assert final_item1.points == 0
        
        # Item 2 lost to item 0, so it should gain back the point: -1 + 1 = 0
        assert final_item2.points == 0
        
        # Item 3 beat item 0, so it should lose the point: +1 - 1 = 0
        assert final_item3.points == 0
        
        # Verify comparisons are deleted
        comparisons = Comparison.query.filter(
            (Comparison.item1_id == item_ids[0]) | (Comparison.item2_id == item_ids[0])
        ).all()
        assert len(comparisons) == 0

def test_reset_item_votes_with_ties(client, sample_collection):
    """Test resetting votes when item has ties (which don't affect points)."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Create comparisons: one win, one tie
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'tie'},
            content_type='application/json'
        )
        
        initial_item0 = db.session.get(Item, item_ids[0])
        initial_points0 = initial_item0.points
        
        # Reset votes
        response = client.delete(f'/api/items/{item_ids[0]}/votes')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['comparisons_reset'] == 2
        
        # Verify points adjusted correctly (only win affects points)
        final_item0 = db.session.get(Item, item_ids[0])
        assert final_item0.points == 0  # Win removed, tie doesn't affect points

def test_change_vote_updates_points(client, sample_collection):
    """Test that changing a vote correctly updates points."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Item 0 beats Item 1
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        initial_item0 = db.session.get(Item, item_ids[0])
        initial_item1 = db.session.get(Item, item_ids[1])
        initial_points0 = initial_item0.points  # Should be 1
        initial_points1 = initial_item1.points  # Should be -1
        
        # Change vote: Item 1 now beats Item 0
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item2'},
            content_type='application/json'
        )
        
        final_item0 = db.session.get(Item, item_ids[0])
        final_item1 = db.session.get(Item, item_ids[1])
        
        # Points should be reversed
        assert final_item0.points == initial_points0 - 2  # Lost the win
        assert final_item1.points == initial_points1 + 2  # Gained the win

def test_change_vote_to_tie(client, sample_collection):
    """Test changing a vote to a tie."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Item 0 beats Item 1
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        initial_item0 = db.session.get(Item, item_ids[0])
        initial_item1 = db.session.get(Item, item_ids[1])
        initial_points0 = initial_item0.points  # Should be 1
        initial_points1 = initial_item1.points  # Should be -1
        
        # Change to tie
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'tie'},
            content_type='application/json'
        )
        
        final_item0 = db.session.get(Item, item_ids[0])
        final_item1 = db.session.get(Item, item_ids[1])
        
        # Points should be reset (ties don't affect points)
        assert final_item0.points == 0
        assert final_item1.points == 0

def test_get_item_votes_after_reset(client, sample_collection):
    """Test that getting votes after reset returns empty lists."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).all()
        item_ids = [item.id for item in items]
        
        # Create comparisons
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Reset votes
        client.delete(f'/api/items/{item_ids[0]}/votes')
        
        # Get votes - should be empty
        response = client.get(f'/api/items/{item_ids[0]}/votes')
        assert response.status_code == 200
        
        data = response.get_json()
        assert len(data['wins']) == 0
        assert len(data['losses']) == 0
        assert len(data['ties']) == 0
        assert data['item']['points'] == 0

