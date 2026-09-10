# Deploying RetailMind

Two targets, same repository: **GitHub** for the source link, **Hugging Face Spaces**
for the live app. The Space builds the Dockerfile itself, generating the warehouse
during the build so cold starts are instant.

---

## 1. GitHub

```bash
gh repo create RetailMind --public --source=. --remote=origin --push
```

Or manually: create an empty repo, then

```bash
git remote add origin https://github.com/Komalpreet2809/RetailMind.git
git push -u origin main
```

## 2. Hugging Face Space

Create the Space first — **SDK: Docker**, hardware: CPU basic (free):

https://huggingface.co/new-space

Name it `RetailMind`. Then push:

```bash
pip install -U huggingface_hub
hf auth login                      # paste a write token from hf.co/settings/tokens

git remote add space https://huggingface.co/spaces/<your-username>/RetailMind
git push space main
```

The Space starts building immediately. Expect **10–20 minutes** on the first build —
most of that is generating 9.4M rows and running the benchmark suite inside the
image. Subsequent pushes that don't touch `scripts/` or `sql/` reuse the cached
layer and deploy in under a minute.

Live URL will be `https://<your-username>-retailmind.hf.space`.

### If the build times out or runs out of disk

Shrink the baked dataset — everything still works, the numbers are just smaller:

```dockerfile
ARG RM_ORDERS=4000000
ARG RM_CUSTOMERS=140000
```

4M orders produces roughly a 900 MB cluster instead of 1.8 GB and halves the build.
The Query Lab re-benchmarks itself during the build, so its figures stay honest to
whatever size actually shipped.

## 3. Custom domain (optional)

Free Spaces don't take custom domains directly. To serve it from
`retailmind.komalpreet.me`, put a rewrite in front of it — the same pattern as a
Vercel `vercel.json`:

```json
{ "rewrites": [{ "source": "/(.*)", "destination": "https://<user>-retailmind.hf.space/$1" }] }
```

Not required. `komalsohal-specula.hf.space` is already on the portfolio in raw form.

---

## Rebuilding the data locally

```bash
docker compose up -d
python scripts/generate.py
docker exec -i retailmind-db psql -U retail -d retailmind -q -f - < sql/04_partition.sql
docker exec -i retailmind-db psql -U retail -d retailmind -q -f - < sql/05_rollups.sql
python scripts/benchmark.py      # -> data/benchmarks.json
python scripts/scaling.py        # -> data/scaling.json  (15-20 min, rebuilds 4x)
```

## Testing the container before pushing

```bash
docker build -t retailmind:full .
docker run --rm -p 7860:7860 retailmind:full
# http://localhost:7860
```
