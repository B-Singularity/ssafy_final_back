import abc
from typing import List, Optional
from .aggregates.movie import Movie
from apps.movie.application.dtos import MovieSearchCriteriaDto, MovieSearchResultDto, PaginationDto

class MovieRepository(abc.ABC):
    @abc.abstractmethod
    def find_by_id(self, movie_id: int) -> Optional[Movie]:
        raise NotImplementedError

    @abc.abstractmethod
    def save(self, movie: Movie) -> Movie:
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self, movie_id: int) -> None:
        raise NotImplementedError

class MovieSearchRepository(abc.ABC):
    @abc.abstractmethod
    def search_movies(self, criteria: MovieSearchCriteriaDto) -> MovieSearchResultDto:
        raise NotImplementedError

    @abc.abstractmethod
    def find_popular_movies(self,
                              list_type_criterion: str,
                              genre_filter: Optional[str],
                              pagination: PaginationDto
                             ) -> MovieSearchResultDto:
        raise NotImplementedError