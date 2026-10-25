"""Owner-authorized New Cards tag-match and explicit planning endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from mtg_helper.auth import get_current_account
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.common import DataResponse
from mtg_helper.models.new_cards import NewCardsResponse
from mtg_helper.services.new_cards.repository import NewCardsError, Owner
from mtg_helper.services.new_cards.service import NewCardsService

router = APIRouter(prefix="/decks/{deck_id}/new-cards", tags=["new-cards"])
Account = Annotated[AccountResponse, Depends(get_current_account)]


def _owner(account: AccountResponse) -> Owner:
    if not account.email:
        raise NewCardsError("Account email required", 403)
    return Owner(account.id, account.email)


def _service(request: Request) -> NewCardsService:
    return NewCardsService(request.app.state.db_pool)


@router.get("")
async def get_cards(
    deck_id: UUID, request: Request, account: Account
) -> DataResponse[NewCardsResponse]:
    return DataResponse(data=await _service(request).view(_owner(account), deck_id))


@router.post("/{oracle_id}/dismiss")
async def dismiss(
    deck_id: UUID, oracle_id: UUID, request: Request, account: Account
) -> DataResponse[NewCardsResponse]:
    service = _service(request)
    owner = _owner(account)
    await service.dismiss(owner, deck_id, oracle_id, undo=False)
    return DataResponse(data=await service.view(owner, deck_id))


@router.delete("/{oracle_id}/dismiss")
async def undo_dismiss(
    deck_id: UUID, oracle_id: UUID, request: Request, account: Account
) -> DataResponse[NewCardsResponse]:
    service = _service(request)
    owner = _owner(account)
    await service.dismiss(owner, deck_id, oracle_id, undo=True)
    return DataResponse(data=await service.view(owner, deck_id))


@router.post("/{oracle_id}/plan")
async def plan(
    deck_id: UUID, oracle_id: UUID, request: Request, account: Account
) -> DataResponse[NewCardsResponse]:
    service = _service(request)
    owner = _owner(account)
    await service.plan(owner, deck_id, oracle_id)
    return DataResponse(data=await service.view(owner, deck_id))
