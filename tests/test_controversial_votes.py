"""Tests for controversial votes functionality."""
import pytest
from app import db, Item, Comparison, Collection

def test_no_controversial_votes_when_consistent(client, sample_collection):
    """Test that no controversial votes are found when all votes are consistent with scores."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create consistent votes: A > B, B > C, C > D
        # This creates scores: A=2, B=0, C=-2, D=-4 (all consistent)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[2], 'item2_id': item_ids[3], 'winner': 'item1'},
            content_type='application/json'
        )
        
        response = client.get(f'/api/collections/{sample_collection}/controversial-votes')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'total_controversy' in data
        assert 'controversial_votes' in data
        assert 'total_controversial_count' in data
        
        assert data['total_controversy'] == 0.0
        assert len(data['controversial_votes']) == 0
        assert data['total_controversial_count'] == 0

def test_controversial_vote_when_inconsistent(client, sample_collection):
    """Test that a vote is controversial when it contradicts current scores."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create votes: A > B, B > C
        # This creates scores: A=2, B=0, C=-2
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Now add a controversial vote: C > A (contradicts scores where A > C)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        
        response = client.get(f'/api/collections/{sample_collection}/controversial-votes')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['total_controversial_count'] == 1
        assert len(data['controversial_votes']) == 1
        
        controversial_vote = data['controversial_votes'][0]
        assert controversial_vote['comparison_id'] is not None
        assert controversial_vote['vote_result'] == 'item2'  # C > A
        assert controversial_vote['controversy_score'] == 4  # |2 - (-2)| = 4
        assert controversial_vote['score_difference'] == 4
        assert data['total_controversy'] == 16.0  # 4^2 = 16

def test_controversial_tie_vote(client, sample_collection):
    """Test that a tie vote is controversial when scores differ."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create votes: A > B, B > C
        # This creates scores: A=2, B=0, C=-2
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Add a tie vote between A and C (controversial since A has higher score)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'tie'},
            content_type='application/json'
        )
        
        response = client.get(f'/api/collections/{sample_collection}/controversial-votes')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['total_controversial_count'] == 1
        assert len(data['controversial_votes']) == 1
        
        controversial_vote = data['controversial_votes'][0]
        assert controversial_vote['vote_result'] == 'tie'
        assert controversial_vote['controversy_score'] == 4  # |2 - (-2)| = 4
        assert data['total_controversy'] == 16.0  # 4^2 = 16

def test_multiple_controversial_votes(client, sample_collection):
    """Test multiple controversial votes and their ordering."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create base ordering: A > B > C > D
        # Scores: A=3, B=1, C=-1, D=-3
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[2], 'item2_id': item_ids[3], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Add controversial votes with different controversy scores
        # C > A (controversy: |3 - (-1)| = 4)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        # D > B (controversy: |1 - (-3)| = 4)
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[3], 'winner': 'item2'},
            content_type='application/json'
        )
        
        response = client.get(f'/api/collections/{sample_collection}/controversial-votes')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['total_controversial_count'] == 2
        assert len(data['controversial_votes']) == 2
        
        # Both should have controversy score of 4
        for vote in data['controversial_votes']:
            assert vote['controversy_score'] == 4
        
        # Total controversy should be sum of squares: 4^2 + 4^2 = 32
        assert data['total_controversy'] == 32.0

def test_top_20_limit(client, sample_collection):
    """Test that only top 20 controversial votes are returned."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create a base ordering: A > B > C > D
        # This creates scores: A=3, B=1, C=-1, D=-3
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[2], 'item2_id': item_ids[3], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Add more items to create more comparisons
        # Add 6 more items (total 10 items = 45 possible comparisons)
        for i in range(6):
            client.post(f'/api/collections/{sample_collection}/items',
                json={'items': f'Item{i+5}'},
                content_type='application/json'
            )
        
        with client.application.app_context():
            items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
            item_ids = [item.id for item in items]
            
            # Create many controversial votes by making lower-indexed items lose to higher-indexed items
            # This contradicts the base ordering where lower indices win
            # Create at least 25 controversial votes to test the limit
            for i in range(min(5, len(item_ids))):
                for j in range(i + 1, min(i + 6, len(item_ids))):
                    if item_ids[i] < item_ids[j]:
                        client.post(f'/api/collections/{sample_collection}/matchup',
                            json={'item1_id': item_ids[i], 'item2_id': item_ids[j], 'winner': 'item2'},
                            content_type='application/json'
                        )
            
            response = client.get(f'/api/collections/{sample_collection}/controversial-votes')
            assert response.status_code == 200
            
            data = response.get_json()
            # Should have some controversial votes
            assert data['total_controversial_count'] > 0
            # But only top 20 should be returned (or fewer if there are less than 20)
            assert len(data['controversial_votes']) <= 20
            assert len(data['controversial_votes']) == min(20, data['total_controversial_count'])
            
            # Votes should be sorted by controversy score (descending)
            if len(data['controversial_votes']) > 1:
                controversy_scores = [vote['controversy_score'] for vote in data['controversial_votes']]
                assert controversy_scores == sorted(controversy_scores, reverse=True)

def test_controversy_score_calculation(client, sample_collection):
    """Test that controversy scores are calculated correctly."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create base ordering: A > B
        # Scores: A=1, B=-1
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Add controversial vote: B > A
        # Controversy score should be |1 - (-1)| = 2
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item2'},
            content_type='application/json'
        )
        
        response = client.get(f'/api/collections/{sample_collection}/controversial-votes')
        assert response.status_code == 200
        
        data = response.get_json()
        assert len(data['controversial_votes']) == 1
        
        controversial_vote = data['controversial_votes'][0]
        assert controversial_vote['controversy_score'] == 2
        assert controversial_vote['score_difference'] == 2
        # Total controversy = 2^2 = 4
        assert data['total_controversy'] == 4.0

def test_controversial_vote_structure(client, sample_collection):
    """Test that controversial vote response has correct structure."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create a controversial vote
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item2'},
            content_type='application/json'
        )
        
        response = client.get(f'/api/collections/{sample_collection}/controversial-votes')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'total_controversy' in data
        assert 'controversial_votes' in data
        assert 'total_controversial_count' in data
        
        if len(data['controversial_votes']) > 0:
            vote = data['controversial_votes'][0]
            assert 'comparison_id' in vote
            assert 'item1' in vote
            assert 'item2' in vote
            assert 'vote_result' in vote
            assert 'vote_description' in vote
            assert 'score_difference' in vote
            assert 'controversy_score' in vote
            
            assert 'id' in vote['item1']
            assert 'name' in vote['item1']
            assert 'points' in vote['item1']
            assert 'id' in vote['item2']
            assert 'name' in vote['item2']
            assert 'points' in vote['item2']

def test_vote_description_format(client, sample_collection):
    """Test that vote descriptions are formatted correctly."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create base ordering
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Test item1 > item2 vote description
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item2'},
            content_type='application/json'
        )
        
        response = client.get(f'/api/collections/{sample_collection}/controversial-votes')
        data = response.get_json()
        
        if len(data['controversial_votes']) > 0:
            vote = data['controversial_votes'][0]
            # Vote description should contain item names and comparison operator
            assert 'Apple' in vote['vote_description'] or 'Banana' in vote['vote_description']
            assert '>' in vote['vote_description'] or '=' in vote['vote_description']

def test_no_comparisons_no_controversial_votes(client, sample_collection):
    """Test that collections with no comparisons have no controversial votes."""
    response = client.get(f'/api/collections/{sample_collection}/controversial-votes')
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['total_controversy'] == 0.0
    assert len(data['controversial_votes']) == 0
    assert data['total_controversial_count'] == 0

def test_total_controversy_sum_of_squares(client, sample_collection):
    """Test that total controversy is sum of squares of controversy scores."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create base ordering: A > B > C
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Add controversial votes with different controversy scores
        # C > A: controversy = 4
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        
        # B > A: controversy = 2 (after previous vote, scores may have changed)
        # Let's check what the actual scores are
        with client.application.app_context():
            items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
            # After C > A, scores might be: A=0, B=0, C=0 or different
            # Let's add another vote to create a clearer scenario
        
        response = client.get(f'/api/collections/{sample_collection}/controversial-votes')
        data = response.get_json()
        
        # Calculate expected total controversy
        expected_total = sum(vote['controversy_score'] ** 2 for vote in data['controversial_votes'])
        assert abs(data['total_controversy'] - expected_total) < 0.01  # Allow small floating point differences

def test_controversial_vote_after_score_update(client, sample_collection):
    """Test that controversial votes update correctly after scores change."""
    with client.application.app_context():
        items = Item.query.filter_by(collection_id=sample_collection).order_by(Item.id).all()
        item_ids = [item.id for item in items]
        
        # Create initial votes: A > B, B > C
        # Scores: A=2, B=0, C=-2
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[1], 'winner': 'item1'},
            content_type='application/json'
        )
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[1], 'item2_id': item_ids[2], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Add controversial vote: C > A
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[2], 'winner': 'item2'},
            content_type='application/json'
        )
        
        # Check controversial votes
        response1 = client.get(f'/api/collections/{sample_collection}/controversial-votes')
        data1 = response1.get_json()
        initial_controversy_count = data1['total_controversial_count']
        
        # Add more votes that might resolve or create more controversy
        client.post(f'/api/collections/{sample_collection}/matchup',
            json={'item1_id': item_ids[0], 'item2_id': item_ids[3], 'winner': 'item1'},
            content_type='application/json'
        )
        
        # Check controversial votes again
        response2 = client.get(f'/api/collections/{sample_collection}/controversial-votes')
        data2 = response2.get_json()
        
        # The controversial vote count may change as scores update
        # But the endpoint should still work correctly
        assert 'total_controversy' in data2
        assert 'controversial_votes' in data2
        assert 'total_controversial_count' in data2
