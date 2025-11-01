# RanQR - Rank Collections by Pairwise Comparisons

A web application that helps you rank large collections of items (hundreds to thousands) through pairwise comparisons. Instead of comparing every item against every other item, RanQR uses a smart algorithm (similar to merge sort) to intelligently propose matchups that will efficiently determine the ranking.

## Features

- **Smart Pairwise Comparisons**: Uses an intelligent algorithm that prioritizes comparisons between items with similar scores, reducing the total number of comparisons needed
- **Point-Based Ranking**: 
  - Win a matchup: +1 point
  - Lose a matchup: -1 point
  - Start at 0 points
  - Tie option available for items that can't be decided
- **Handle Inconsistencies**: The point system naturally handles cycles (A > B > C > A) by averaging out through multiple comparisons
- **Progress Tracking**: See how many comparisons you've made vs. the maximum possible
- **Clean UI**: Modern, responsive interface for easy ranking

## Quick Start

### Prerequisites

- Docker installed on your system

### Running with Docker

1. Clone this repository:
   ```bash
   git clone <repository-url>
   cd ranqr
   ```

2. Build and run with Docker:
   ```bash
   docker-compose up --build
   ```

   Or using Docker directly:
   ```bash
   docker build -t ranqr .
   docker run -p 5000:5000 -v $(pwd)/data:/app/data ranqr
   ```

3. Open your browser and navigate to:
   ```
   http://localhost:5000
   ```

That's it! No additional setup required.

## Usage

1. **Create a Collection**: Enter a name and paste your items (one per line)
2. **Make Comparisons**: Click "Make Comparisons" and decide between pairwise matchups
3. **View Rankings**: See your ranked list at any time, sorted by points
4. **Continue Ranking**: Keep making comparisons to refine your rankings

## How It Works

The algorithm prioritizes matchups based on:
- **Score Difference**: Items with similar scores are compared first (like merge sort comparing adjacent elements)
- **Comparison Count**: Items with fewer comparisons get priority to ensure balanced coverage

This approach significantly reduces the number of comparisons needed compared to the naive O(n²) approach, especially as you make more decisions and the ranking becomes clearer.

## Technical Details

- **Backend**: Flask (Python)
- **Database**: SQLite (stored in `./data/` directory)
- **Frontend**: Vanilla HTML/CSS/JavaScript
- **Containerization**: Docker with volume mounting for data persistence

## Data Persistence

Your collections and rankings are stored in SQLite database files in the `./data/` directory. This directory is mounted as a volume, so your data persists even if you rebuild the container.

**Note:** The `./data/` directory will be created automatically when you first run the application. If you encounter permission issues, ensure the directory exists and has appropriate permissions:
```bash
mkdir -p data
```

## Testing

The application includes comprehensive tests to verify functionality and catch syntax errors. Run tests with:

```bash
# Using docker-compose
docker-compose run --rm web pytest

# Or using Make (if available)
make test
```

Tests cover:
- Collection and item management
- Matchup logic and point calculations
- Smart algorithm behavior
- Edge cases (ties, updates, cycles)
- Ranking correctness

## License

See LICENSE file for details.
