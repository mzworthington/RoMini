from collections.abc import Callable
from inspect import iscoroutinefunction

from fastapi import FastAPI, Request


def bind(ctx: object, handler: Callable[..., object]) -> Callable[..., object]:
    if iscoroutinefunction(handler):

        async def endpoint(request: Request):
            return await handler(ctx, request)

    else:

        def endpoint(request: Request):
            return handler(ctx, request)

    endpoint.__name__ = handler.__name__
    return endpoint


def bind_bare(ctx: object, handler: Callable[..., object]) -> Callable[..., object]:
    def endpoint():
        return handler(ctx)

    endpoint.__name__ = handler.__name__
    return endpoint


def mount_routes(app: FastAPI, ctx: object, specs: list[tuple]) -> None:
    for path, methods, handler, bare, options in specs:
        endpoint = bind_bare(ctx, handler) if bare else bind(ctx, handler)
        app.add_api_route(path, endpoint, methods=list(methods), **options)
