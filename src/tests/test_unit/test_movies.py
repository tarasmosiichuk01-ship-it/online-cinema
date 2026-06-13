from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_movie_list_prev_page_not_none(client, test_movie):
    """
    Test that prev_page is not None when page=2.

    Ensures that the pagination returns a valid prev_page link
    when the requested page is greater than 1 and total items
    exceed per_page.
    """
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 15

    mock_movies_result = MagicMock()
    mock_movies_result.scalars.return_value.all.return_value = [test_movie]

    with patch(
        "routes.cinema.movies.AsyncSession.execute",
        side_effect=[mock_count_result, mock_movies_result]
    ):
        response = await client.get("/api/v1/cinema/movies?page=2&per_page=10")

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["prev_page"] is not None
    assert "page=1" in response_data["prev_page"]


@pytest.mark.asyncio
async def test_get_movie_list_next_page_not_none(client, test_movie):
    """
    Test that next_page is not None when there is a next page.

    Ensures that the pagination returns a valid next_page link
    when the current page is less than total pages.
    """
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 15

    mock_movies_result = MagicMock()
    mock_movies_result.scalars.return_value.all.return_value = [test_movie]

    with patch(
        "routes.cinema.movies.AsyncSession.execute",
        side_effect=[mock_count_result, mock_movies_result]
    ):
        response = await client.get("/api/v1/cinema/movies?page=1&per_page=10")

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["next_page"] is not None
    assert "page=2" in response_data["next_page"]


@pytest.mark.asyncio
async def test_get_movie_list_next_page_and_prev_page_not_none(client, test_movie):
    """
    Test that both prev_page and next_page are not None on a middle page.

    Ensures that the pagination returns valid prev_page and next_page links
    when the current page is neither the first nor the last page.
    """
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 25

    mock_movies_result = MagicMock()
    mock_movies_result.scalars.return_value.all.return_value = [test_movie]

    with patch(
        "routes.cinema.movies.AsyncSession.execute",
        side_effect=[mock_count_result, mock_movies_result]
    ):
        response = await client.get("/api/v1/cinema/movies?page=2&per_page=10")

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["prev_page"] is not None
    assert response_data["next_page"] is not None
    assert "page=1" in response_data["prev_page"]
    assert "page=3" in response_data["next_page"]


@pytest.mark.asyncio
async def test_get_movie_list_total_pages_is_right(client, test_movie):
    """
    Test that total_pages is calculated correctly.

    Ensures that total_pages equals 2 when total_items=11 and per_page=10,
    verifying that math.ceil is applied correctly.
    """
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 11

    mock_movies_result = MagicMock()
    mock_movies_result.scalars.return_value.all.return_value = [test_movie]

    with patch(
        "routes.cinema.movies.AsyncSession.execute",
        side_effect=[mock_count_result, mock_movies_result]
    ):
        response = await client.get("/api/v1/cinema/movies?page=1&per_page=10")

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["total_pages"] is not None
    assert response_data["total_pages"] == 2



