"""Memory API routes (split from the former monolithic router)."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status

from negotium.app.api._shared import (
    _archive_document_index,
    _audit,
    _complete_office_task,
    _context_compression_prompt,
    _lines_from_markdown,
    _memory_refresh_prompt,
    _read_archive_document,
    _readable_context_bundle,
    _readable_source_payload,
    _require,
    _volatile_memories_markdown,
)
from negotium.app.container import Container
from negotium.app.schemas.core import (
    ContextCompressRequest,
    DeletionRequestPayload,
    DocumentReadPayload,
    MemoryRefreshRequest,
    MemorySchemaPayload,
    MemorySchemaProposalPayload,
    OperationsMemoryPayload,
    PromoteMemoryPayload,
    ReadableContextBundlePayload,
    ReadableContextPreviewRequest,
    ReadableContextSourcePayload,
    VolatileMemoryPayload,
    WorkMemoryPayload,
)
from negotium.archive.context_compressor import CompressedContext
from negotium.archive.deletion_requests import DeletionRequest
from negotium.archive.volatile_memory import MemoryScope, VolatileMemory


def create_memory_router(container: Container) -> APIRouter:
    """Routes for the memory domain."""
    router = APIRouter()

    @router.get("/memory/permanent/sources")
    async def list_permanent_sources(
        limit: int = 50,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {"sources": container.permanent_memory.recent(limit=max(1, min(limit, 200)))}

    @router.get("/memory/permanent/recent")
    async def recent_permanent_memory(
        limit: int = 50,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {"sources": container.permanent_memory.recent(limit=max(1, min(limit, 200)))}

    @router.get("/memory/permanent/search")
    async def search_permanent_memory(
        q: str = "",
        limit: int = 50,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {"sources": container.permanent_memory.search(q, limit=max(1, min(limit, 200)))}

    @router.get("/memory/readable-sources")
    async def list_readable_sources(
        q: str = "",
        limit: int = 100,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        source_limit = max(1, min(limit, 300))
        sources = (
            container.permanent_memory.search(q, limit=source_limit)
            if q.strip()
            else container.permanent_memory.recent(limit=source_limit)
        )
        return {
            "sources": [
                _readable_source_payload(source, selected=False, order=index).model_dump()
                for index, source in enumerate(sources)
            ]
        }

    @router.get("/memory/readable-source")
    async def read_readable_source(
        source_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> ReadableContextSourcePayload:
        _require(container, x_ng_user, "work:read")
        try:
            source = container.permanent_memory.read_source(source_id)
        except FileNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="source not found") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return _readable_source_payload(source, selected=True, order=0)

    def _delete_memory_source_by_id(source_id: str, actor: str) -> dict[str, object]:
        physical_deleted = True
        try:
            deleted = container.permanent_memory.delete_source(source_id)
        except FileNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="source not found") from exc
        except ValueError as exc:
            if "cannot be deleted from the memory UI" not in str(exc):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            try:
                deleted = container.permanent_memory.read_source(source_id, max_chars=1)
            except FileNotFoundError as read_exc:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, detail="source not found"
                ) from read_exc
            except ValueError as read_exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(read_exc)) from read_exc
            physical_deleted = False
        request = container.deletion_requests.create(
            DeletionRequest.create(
                requester=actor,
                target_type=str(deleted.get("kind") or "source"),
                target_id=str(deleted.get("id") or source_id),
                summary=str(deleted.get("title") or source_id),
                source_path=str(deleted.get("path") or source_id),
                sensitivity="internal",
                reason="관리자 즉시 삭제" if physical_deleted else "관리자 즉시 숨김",
            )
        )
        decided = container.deletion_requests.decide(request.id, actor=actor, approved=True)
        _audit(
            container,
            actor=actor,
            action="memory.source.delete",
            target=str(deleted.get("kind") or "source"),
            target_id=str(deleted.get("id") or source_id),
            details={"physical_deleted": physical_deleted},
        )
        return {
            "ok": True,
            "source": deleted,
            "request": decided.to_dict(),
            "physical_deleted": physical_deleted,
        }

    @router.delete("/memory/sources")
    async def delete_memory_source_query(
        source_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        return _delete_memory_source_by_id(source_id, actor)

    @router.delete("/memory/sources/{source_id:path}")
    async def delete_memory_source_path(
        source_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        return _delete_memory_source_by_id(source_id, actor)

    @router.post("/memory/readable-context/preview")
    async def preview_readable_context(
        payload: ReadableContextPreviewRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> ReadableContextBundlePayload:
        _require(container, x_ng_user, "work:read")
        return _readable_context_bundle(container, payload)

    @router.post("/memory/permanent/promote")
    async def promote_permanent_memory(
        payload: PromoteMemoryPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        promoted = container.permanent_memory.promote(
            title=payload.title,
            content=payload.content,
            source_refs=payload.source_refs,
            actor=actor,
        )
        _audit(
            container,
            actor=actor,
            action="memory.promote",
            target="permanent_memory",
            target_id=str(promoted["path"]),
        )
        return {"ok": True, "memory": promoted}

    @router.get("/memory/conversations")
    async def list_conversations(
        user_id: str | None = None,
        limit: int = 100,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "work:read")
        requested_user = (
            user_id if container.access_control.has_permission(actor, "admin:users") else actor
        )
        return {
            "records": container.conversations.list_recent(
                user_id=requested_user, limit=max(1, min(limit, 500))
            )
        }

    @router.get("/memory/volatile")
    async def list_volatile_memory(
        scope: MemoryScope | None = None,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {"memories": container.volatile_memory.list(scope=scope)}

    @router.get("/memory/volatile/{scope}/{key}")
    async def read_volatile_memory(
        scope: MemoryScope,
        key: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> VolatileMemoryPayload:
        _require(container, x_ng_user, "work:read")
        return VolatileMemoryPayload.from_memory(
            container.volatile_memory.read(scope=scope, key=key)
        )

    @router.put("/memory/volatile/{scope}/{key}")
    async def write_volatile_memory(
        scope: MemoryScope,
        key: str,
        payload: VolatileMemoryPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> VolatileMemoryPayload:
        actor = _require(container, x_ng_user, "memory:write")
        memory = payload.to_memory()
        saved = container.volatile_memory.write(
            VolatileMemory.from_mapping({**memory.to_dict(), "scope": scope, "key": key})
        )
        _audit(
            container,
            actor=actor,
            action="memory.volatile.upsert",
            target="volatile_memory",
            target_id=f"{scope}:{key}",
        )
        return VolatileMemoryPayload.from_memory(saved)

    @router.delete("/memory/volatile/{scope}/{key}")
    async def delete_volatile_memory(
        scope: MemoryScope,
        key: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        ok = container.volatile_memory.delete(scope=scope, key=key)
        _audit(
            container,
            actor=actor,
            action="memory.volatile.delete",
            target="volatile_memory",
            target_id=f"{scope}:{key}",
        )
        return {"ok": ok}

    @router.post("/memory/volatile/refresh")
    async def refresh_volatile_memory(
        payload: MemoryRefreshRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> VolatileMemoryPayload:
        actor = _require(container, x_ng_user, "llm:chat")
        key = payload.key.strip() or actor
        lim = max(1, min(payload.source_limit, 50))
        sources = container.permanent_memory.resolve_sources(
            query=payload.query,
            limit=lim,
            source_ids=payload.source_ids if payload.source_ids else None,
        )
        if not sources:
            sources = container.permanent_memory.search(payload.query, limit=lim)
        prompt = _memory_refresh_prompt(payload.query, sources)
        summary = await _complete_office_task(container, prompt, task="memory_summary")
        saved = container.volatile_memory.write(
            VolatileMemory(
                scope=payload.scope,
                key=key,
                summary=summary,
                current_intent=payload.query,
                relevant_sources=[str(source["path"]) for source in sources],
            )
        )
        _audit(
            container,
            actor=actor,
            action="memory.volatile.refresh",
            target="volatile_memory",
            target_id=f"{payload.scope}:{key}",
        )
        return VolatileMemoryPayload.from_memory(saved)

    @router.post("/memory/context/compress")
    async def compress_context_memory(
        payload: ContextCompressRequest,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "llm:chat")
        key = payload.key.strip() or actor
        lim = max(1, min(payload.source_limit, 50))
        sources = container.permanent_memory.resolve_sources(
            query=payload.query,
            limit=lim,
            source_ids=payload.source_ids if payload.source_ids else None,
        )
        if not sources:
            sources = container.permanent_memory.search(payload.query, limit=lim)
        volatile_md = ""
        if payload.include_volatile:
            volatile_md = _volatile_memories_markdown(container)
        prompt = _context_compression_prompt(
            payload.query,
            payload.token_budget,
            sources,
            volatile_appendix=volatile_md,
        )
        summary = await _complete_office_task(container, prompt, task="memory_summary")
        saved = container.compressed_context.write(
            CompressedContext(
                scope=payload.scope,
                key=key,
                summary=summary,
                facts=_lines_from_markdown(summary, prefix="-"),
                source_refs=[str(source["path"]) for source in sources],
                token_budget=payload.token_budget,
            )
        )
        _audit(
            container,
            actor=actor,
            action="memory.context.compress",
            target="compressed_context",
            target_id=f"{payload.scope}:{key}",
        )
        volatile_refs = (
            [f"{item['scope']}:{item['key']}" for item in container.volatile_memory.list()]
            if payload.include_volatile
            else []
        )
        return {
            "context": saved.to_dict(),
            "used_sources": sources,
            "volatile_memories": volatile_refs,
        }

    @router.get("/memory/context/compressed")
    async def read_compressed_context(
        scope: MemoryScope = "global",
        key: str = "default",
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {"context": container.compressed_context.read(scope=scope, key=key).to_dict()}

    @router.get("/memory/schema")
    async def list_memory_schema(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "work:read")
        return {
            "schemas": container.memory_schema.list(),
            "proposals": container.memory_schema.proposals(),
        }

    @router.post("/memory/schema")
    async def upsert_memory_schema(
        payload: MemorySchemaPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        schema = container.memory_schema.upsert(payload.to_record(actor=actor), actor=actor)
        _audit(
            container,
            actor=actor,
            action="memory.schema.upsert",
            target="memory_schema",
            target_id=schema.type_id,
        )
        return {"ok": True, "schema": schema.to_dict(), "schemas": container.memory_schema.list()}

    @router.post("/memory/schema/propose")
    async def propose_memory_schema(
        payload: MemorySchemaProposalPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        proposal = container.memory_schema.propose(
            actor=actor, mode=payload.mode, proposal=payload.proposal
        )
        _audit(
            container,
            actor=actor,
            action="memory.schema.propose",
            target="memory_schema_proposal",
            target_id=str(proposal["id"]),
        )
        return {"ok": True, "proposal": proposal}

    @router.post("/memory/schema/proposals/{proposal_id}/approve")
    async def approve_memory_schema(
        proposal_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        proposal = container.memory_schema.approve(proposal_id, actor=actor)
        _audit(
            container,
            actor=actor,
            action="memory.schema.approve",
            target="memory_schema_proposal",
            target_id=proposal_id,
        )
        return {"ok": True, "proposal": proposal, "schemas": container.memory_schema.list()}

    @router.post("/memory/schema/code-proposals")
    async def create_memory_schema_code_proposal(
        payload: MemorySchemaProposalPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        proposal = container.memory_schema.propose(
            actor=actor, mode="llm_code_write", proposal=payload.proposal
        )
        _audit(
            container,
            actor=actor,
            action="memory.schema.code_propose",
            target="memory_schema_proposal",
            target_id=str(proposal["id"]),
        )
        return {"ok": True, "proposal": proposal}

    @router.get("/memory/deletion-requests")
    async def list_deletion_requests(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "admin:users")
        return {"requests": container.deletion_requests.list()}

    @router.post("/memory/deletion-requests")
    async def create_deletion_request(
        payload: DeletionRequestPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "memory:write")
        request = container.deletion_requests.create(
            DeletionRequest.create(**payload.model_dump(), requester=actor)
        )
        _audit(
            container,
            actor=actor,
            action="memory.delete_requested",
            target=payload.target_type,
            target_id=payload.target_id,
        )
        return {"ok": True, "request": request.to_dict()}

    @router.post("/memory/deletion-requests/{request_id}/approve")
    async def approve_deletion_request(
        request_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        pending = container.deletion_requests.get(request_id)
        if pending is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="deletion request not found")
        if pending.status != "pending":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="deletion request already decided"
            )
        source_id = pending.source_path or pending.target_id
        try:
            container.permanent_memory.delete_source(source_id)
        except FileNotFoundError:
            # Some older requests point to record ids or already-removed files.
            # Keep the approval/tombstone trail so scans stop surfacing them.
            pass
        except ValueError as exc:
            if "cannot be deleted from the memory UI" not in str(exc):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        request = container.deletion_requests.decide(request_id, actor=actor, approved=True)
        _audit(
            container,
            actor=actor,
            action="memory.delete_approved",
            target=request.target_type,
            target_id=request.target_id,
        )
        return {"ok": True, "request": request.to_dict()}

    @router.post("/memory/deletion-requests/{request_id}/reject")
    async def reject_deletion_request(
        request_id: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        actor = _require(container, x_ng_user, "admin:users")
        request = container.deletion_requests.decide(request_id, actor=actor, approved=False)
        _audit(
            container,
            actor=actor,
            action="memory.delete_rejected",
            target=request.target_type,
            target_id=request.target_id,
        )
        return {"ok": True, "request": request.to_dict()}

    @router.get("/operations-memory")
    async def read_operations_memory() -> OperationsMemoryPayload:
        memory = container.operations_memory.read()
        return OperationsMemoryPayload(**memory.to_dict())

    @router.put("/operations-memory")
    async def write_operations_memory(
        payload: OperationsMemoryPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> OperationsMemoryPayload:
        actor = _require(container, x_ng_user, "memory:write")
        memory = payload.to_memory()
        container.operations_memory.write(memory)
        _audit(
            container, actor=actor, action="operations_memory.update", target="operations_memory"
        )
        return OperationsMemoryPayload(**memory.to_dict())

    @router.get("/work-memory")
    async def read_work_memory(
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> WorkMemoryPayload:
        _require(container, x_ng_user, "work:read")
        return WorkMemoryPayload.from_memory(container.work_memory.read())

    @router.put("/work-memory")
    async def write_work_memory(
        payload: WorkMemoryPayload,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> WorkMemoryPayload:
        actor = _require(container, x_ng_user, "memory:write")
        memory = container.work_memory.write(payload.to_memory())
        _audit(container, actor=actor, action="work_memory.update", target="work_memory")
        return WorkMemoryPayload.from_memory(memory)

    @router.get("/archive/documents")
    async def read_archive_document(
        path: str,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> DocumentReadPayload:
        _require(container, x_ng_user, "documents:read")
        try:
            return _read_archive_document(container, path)
        except FileNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @router.get("/archive/document-index")
    async def list_archive_document_index(
        q: str = "",
        limit: int = 200,
        x_ng_user: str | None = Header(default=None, alias="X-NG-User"),
    ) -> dict[str, object]:
        _require(container, x_ng_user, "documents:read")
        return {"documents": _archive_document_index(container, q=q, limit=max(1, min(limit, 500)))}

    return router
