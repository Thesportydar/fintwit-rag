import json

import pytest

from src.handler import lambda_handler


pytestmark = pytest.mark.integration


def test_lambda_handler_live_response_envelope():
    response = lambda_handler(
        {
            "body": json.dumps(
                {
                    "query": "bitcoin",
                    "retrieve_limit": 3,
                    "top_n": 2,
                }
            )
        },
        None,
    )

    assert response["statusCode"] == 200
    assert response["headers"] == {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
    }

    payload = json.loads(response["body"])
    assert set(payload) == {"answer", "sources"}
    assert isinstance(payload["answer"], str)
    assert isinstance(payload["sources"], list)

    for source in payload["sources"]:
        assert set(source) == {"url", "handle", "date", "content"}
        assert isinstance(source["date"], str)


def test_lambda_handler_live_error_contract():
    response = lambda_handler({"body": json.dumps({"top_n": 0})}, None)

    assert response["statusCode"] == 400
    payload = json.loads(response["body"])
    assert payload == {"error": "El campo 'query' es requerido"}
