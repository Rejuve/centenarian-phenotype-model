# Deployment — endpoints & client integration

One service (`centenarian_phenotype.api:app`) serves three consumers. The scoring core is
dependency-light and stateless, so it runs equally well as a long-lived container or AWS Lambda.

| Consumer | Layer | Routes |
|---|---|---|
| HTML survey widget (browser) | 1 | `GET /v1/quiz/1`, `POST /v1/score/layer1` |
| Rejuve Longevity App (Flutter) | 2 | `GET /v1/quiz/2`, `POST /v1/score/layer2` |
| Premium clinical | 3 | `POST /v1/score/layer3` |

Every consumer **renders from `GET /v1/quiz/{layer}`** (ids, text, option labels+indices) and
**submits answers as `{question_id: option_index}`** — so no frontend hard-codes questions or drifts
from the model. Layer 3 additionally sends `clinical: {feature: alignment_0_1}`.

## Each layer deploys independently

The scoring core loads only the model it needs (L1 → `tier1` only; L2 → `tier2`; L3 → `tier2` +
`tier3`), and `create_app(layers)` builds a service exposing **only** the chosen layers — any other
layer's routes are absent / 404. So you can host the surfaces separately with different access:

| Deployment | Build | Routes | Access |
|---|---|---|---|
| **Web widget / ads** (L1) | `create_app([1])` → `app_widget` / `handler_widget` | quiz/1, score/layer1 | public, CORS-open, no auth, high-volume |
| **Web survey** (L2) | `create_app([2])` → `app_survey` / `handler_survey` | quiz/2, score/layer2 | public or gated |
| **Rejuve app backend** (L2+L3) | `create_app([2,3])` → `app_app` / `handler_app` | quiz/2, score/layer2, score/layer3 | authenticated (app-only); **L3 lives here exclusively** |
| All-in-one | `create_app([1,2,3])` → `app` / `handler` | everything | single service |

```bash
# three independent services, each scoped + access-controlled separately
uvicorn "centenarian_phenotype.api:app_widget"  # L1 — public web/ads
uvicorn "centenarian_phenotype.api:app_survey"  # L2 — web survey
uvicorn "centenarian_phenotype.api:app_app"     # L2+L3 — Rejuve app (L3 never exposed to web)
```
A widget deployment physically cannot serve Layer 3 (the route isn't registered), so the premium
clinical layer stays app-exclusive by construction, not just by convention. The three model YAMLs are
tiny and bundled together, so every shape is self-contained.

## Run locally

```bash
pip install -e ".[api]"
uvicorn centenarian_phenotype.api:app --reload      # http://127.0.0.1:8000/docs
```

## Layer 1 → HTML widget (CORS)

The widget is browser JavaScript, so CORS must allow its origin. Set it via env var (comma-separated):

```bash
export CENTENARIAN_CORS_ORIGINS="https://rejuve.ai,https://www.rejuve.ai"
```

Widget flow:
```js
const quiz  = await (await fetch(`${API}/v1/quiz/1`)).json();      // render questions
const body  = { answers: { q_physical_activity: 0, q_diet: 1, /* ... */ } };
const result = await (await fetch(`${API}/v1/score/layer1`, {
  method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
})).json();
// result.score_pct, result.confidence_pct (=30), result.narrative, result.evidence_basis_pct
```

## Layer 2 → Rejuve Longevity App (Flutter + AWS)

Recommended AWS shape: **API Gateway (HTTP API) → Lambda**, using the bundled Mangum adapter.

```bash
pip install -e ".[aws]"          # fastapi + mangum
# handler entry point: centenarian_phenotype.api.handler
```

**SAM template sketch** (`template.yaml`):
```yaml
Resources:
  ScoreFn:
    Type: AWS::Serverless::Function
    Properties:
      Handler: centenarian_phenotype.api.handler
      Runtime: python3.12
      MemorySize: 256
      Timeout: 10
      Events:
        Api:
          Type: HttpApi
          Properties: { Path: /{proxy+}, Method: ANY }
      Environment:
        Variables:
          CENTENARIAN_CORS_ORIGINS: "https://rejuve.ai"
```
Deploy: `sam build && sam deploy --guided`. Put the model behind API Gateway **auth (API key / Cognito)
and throttling**; the app calls `POST /v1/score/layer2`.

Flutter call:
```dart
final quiz = await http.get(Uri.parse('$api/v1/quiz/2'));            // render
final res  = await http.post(Uri.parse('$api/v1/score/layer2'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'answers': answers}));                          // {qid: index}
// res.body -> score_pct, confidence_pct (=50), subscores, evidence_basis_pct, ...
```

Packaging notes for Lambda: the 3 model YAMLs are package data (`importlib.resources`) — they ship
inside the deployment artifact, so there is no `data/` dependency at runtime. Only `pyyaml`,
`fastapi`, and `mangum` are needed. Cold-start is small (models load + cache on first call).

## Alternatives
- **Container** (ECS Fargate / App Runner): run `uvicorn centenarian_phenotype.api:app` in a
  slim Python image; same routes, no Mangum.
- **Direct library** (no HTTP): import `centenarian_phenotype.score(...)` inside an existing service.

## Contract & invariants
See `docs/scoring_api.md`. Regression guard: `python -m pytest tests/` (scoring + API).
