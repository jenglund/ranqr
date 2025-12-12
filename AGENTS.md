# Agent Instructions for ranqr

## Running Tests

```bash
make test
```

This runs the full test suite via Docker Compose. The tests use an in-memory SQLite database to ensure isolation from production data.

## Project Structure

- `app.py` - Main Flask application with API endpoints
- `templates/` - HTML templates for the web interface  
- `tests/` - Test suite using pytest
- `Makefile` - Build and test commands
- `docker-compose.yml` - Container orchestration

## Development

The application is a Flask-based ranking tool that uses pairwise comparisons to rank items. Key features include:

- Collections of items to rank
- Pairwise matchup voting
- Scoring system with tie-breaking via sub-scores
- Controversial vote detection
- Triangle (cyclic inconsistency) detection
- Export/import functionality

