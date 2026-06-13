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