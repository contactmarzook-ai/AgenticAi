# Deploying Star Dust

Three components, all built from this repository:

| Image | Built from | Runs |
|---|---|---|
| `agentos-api` | `backend/Dockerfile` | the API (`uvicorn`), database migrations, and the scheduler (`python -m app.scheduler`) |
| `agentos-web` | `frontend/Dockerfile` | nginx serving the UI (and proxying `/api` when there is no ingress) |

Plus PostgreSQL 14+ and at least one OpenAI-compatible LLM endpoint.

## Docker Compose

For a single server (PostgreSQL, Ollama, API, scheduler, web):

```bash
cp .env.example .env        # set POSTGRES_PASSWORD, JWT_SECRET, CREDENTIALS_KEY, BOOTSTRAP_ADMIN_PASSWORD
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5:7b-instruct
```

Open `http://<server>:8080` and sign in with the bootstrap admin. Put a TLS-terminating reverse
proxy in front of port 8080 before exposing it beyond a trusted network.

## Kubernetes

Manifests are plain Kustomize (`kubectl apply -k`), in `deploy/k8s`:

```
base/                    api (Deployment+Service+HPA+PDB), scheduler, web, ingress, network policies
components/ollama/       optional in-cluster Ollama (StatefulSet + 50Gi PVC)
overlays/production/     namespace, image tags, hostname/TLS, settings  ← edit this
```

### 1. Prerequisites

- An ingress controller. The manifests assume **ingress-nginx** in namespace `ingress-nginx`
  (the network policies allow traffic from that namespace). Change `ingressClassName` and the
  `namespaceSelector` in `base/networkpolicy.yaml` if you use something else.
- **PostgreSQL**: use your cloud's managed service (RDS, Cloud SQL, Azure Database). Create a
  database and a user that owns it. Enable automated backups there.
- **An LLM endpoint**: either enable `components/ollama` (needs a GPU node for useful speed),
  or point at an existing vLLM/Ollama/hosted endpoint.
- Optional: cert-manager for TLS.

### 2. Build and push images

CI (`.github/workflows/ci.yml`) builds both images and pushes them to GHCR when you push a tag
like `v1.0.0`. To build by hand:

```bash
docker build -t REGISTRY/agentos-api:1.0.0 backend  && docker push REGISTRY/agentos-api:1.0.0
docker build -t REGISTRY/agentos-web:1.0.0 frontend && docker push REGISTRY/agentos-web:1.0.0
```

### 3. Create the secret

The manifests expect a Secret named `agentos-secrets` in the namespace. Create it with your
secret manager (External Secrets, Sealed Secrets, Vault), or directly:

```bash
kubectl create namespace agentos
kubectl -n agentos create secret generic agentos-secrets \
  --from-literal=DATABASE_URL='postgresql+psycopg://agentos:PASSWORD@db-host:5432/agentos?sslmode=require' \
  --from-literal=JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  --from-literal=CREDENTIALS_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  --from-literal=BOOTSTRAP_ADMIN_EMAIL='admin@yourcompany.com' \
  --from-literal=BOOTSTRAP_ADMIN_PASSWORD='a-strong-initial-password'
```

`CREDENTIALS_KEY` encrypts saved connections (SMTP passwords, API keys, webhook URLs). Keep a
copy in your secret manager: if it is lost or changed, saved connections can no longer be read.

The bootstrap admin is only created while the users table is empty. After the first sign-in,
change that password (sidebar → Change password) and you can remove the two `BOOTSTRAP_*` keys.

For Microsoft Entra ID sign-in add `--from-literal=OIDC_CLIENT_SECRET=...` to the Secret and fill
the `OIDC_*` lines in the ConfigMap (see `docs/SECURITY_MODEL.md`). The API pods need outbound HTTPS
to `login.microsoftonline.com`. Sessions use a Secure cookie, so serve the app over HTTPS.

The bootstrap admin is a **platform admin** in the "Default organization". Create further
organizations and their org admins under **Users**.

LLM API keys (for hosted endpoints) go in the same Secret under a name starting with `LLM_KEY_`, e.g. `LLM_KEY_VLLM`;
on the Models page set the provider's "API key environment variable" to that name.

### 4. Configure and apply

Edit `overlays/production/kustomization.yaml` (every line marked `CHANGE`): namespace, image
names/tags, hostname, TLS, `LLM_BASE_URL`/`LLM_DEFAULT_MODEL`, and remove the Ollama component if
you don't run it in-cluster. Then:

```bash
kubectl kustomize deploy/k8s/overlays/production | less    # review
kubectl apply -k deploy/k8s/overlays/production
kubectl -n agentos rollout status deploy/agentos-api
```

If you use in-cluster Ollama, pull a model once:

```bash
kubectl -n agentos exec statefulset/ollama -- ollama pull qwen2.5:7b-instruct
```

Then sign in at `https://<your host>`, open **Models**, press **Test** on the provider, and
create users under **Users**.

### How it behaves

- **Migrations** run in an init container of each API pod (`alembic upgrade head`). They take
  a PostgreSQL advisory lock, so pods starting together don't conflict. A rollout with a
  migration therefore applies it before the new pods serve traffic.
- **Scaling**: the API is stateless (all state in PostgreSQL) and autoscaled 2–6 pods on CPU.
  Each pod runs `WEB_CONCURRENCY` worker processes. The scheduler runs as one pod; more replicas
  are safe but unnecessary.
- **Long requests**: agent runs can take minutes on local models, so the ingress timeouts are
  600s. Workflows started via the API or triggers run in the background; clients poll
  `GET /api/runs/{id}`.
- **Pod security**: all Star Dust containers run as non-root with a read-only root filesystem,
  no privilege escalation and all capabilities dropped. The namespace enforces the `baseline`
  Pod Security Standard and warns on `restricted`, because the Ollama image runs as root. If
  you don't run Ollama in this namespace, set `enforce: restricted`.
- **Network policies** restrict ingress to the API and web pods (and Ollama). Egress is open
  because database and LLM addresses vary; restrict it in your overlay if your cluster requires.
- **Logs** are JSON on stdout (request id, user id, path, status, duration), suitable for any
  log collector. Every response carries an `X-Request-ID`, which is also stored in audit rows.
- **Health**: `/healthz` (liveness) and `/readyz` (checks the database).

### Upgrades and rollback

Apply the overlay with the new image tag. Rolling updates keep at least the current pods
serving (`maxUnavailable: 0`). Because old and new pods briefly run side by side,
write schema changes so the previous version still works (add columns before using them,
remove them a release later). To roll back across a migration, run
`alembic downgrade <revision>` from an API pod first, then apply the previous tag.

### Backups

Everything (users, agents, workflows, runs, audit log) is in PostgreSQL. Use your managed
database's automated backups and point-in-time recovery. The Ollama PVC only holds model files,
which can be pulled again.
