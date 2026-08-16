"""Aggregates every v1 endpoint module into one router."""

from fastapi import APIRouter

from app.api.deps import AuthenticatedRoute
from app.api.v1.endpoints import conversions, fasta, fastq, files, formats, sequences

api_router = APIRouter(dependencies=AuthenticatedRoute)

api_router.include_router(sequences.router)
api_router.include_router(fasta.router)
api_router.include_router(fastq.router)
api_router.include_router(files.router)
api_router.include_router(conversions.router)
api_router.include_router(formats.router)
