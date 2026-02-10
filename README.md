# Fronius Primo Exporter

Exporter **Prometheus** pour onduleur Fronius (modèle Primo ou tout appareil exposant la [Fronius Solar API](https://www.fronius.com/en/solar-energy/installers-partners/technical-data/all-products/system-monitoring/open-interfaces/fronius-solar-api-json-)).

Avec un **Fronius Primo**, l’API est en général accessible via un **Datamanager 2.0** ou **Datalogger Web** sur le réseau.

---

## Prérequis

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/)
- Fronius (onduleur ou Datamanager) accessible en HTTP sur le réseau

---

## Installation

```bash
git clone https://github.com/tom-da-costa/fronius_primo_exporter.git
cd fronius_primo_exporter
uv sync
```

---

## Docker

L’image est publiée sur le GitHub Container Registry à chaque push sur `master` et à chaque release.

```bash
# Dernière version (branch master)
docker pull ghcr.io/tom-da-costa/fronius_primo_exporter:latest

# Version spécifique (ex. 1.0.0)
docker pull ghcr.io/tom-da-costa/fronius_primo_exporter:1.0.0

# Lancer l’exporter
docker run -p 9687:9687 ghcr.io/tom-da-costa/fronius_primo_exporter:latest --fronius-url http://192.168.1.10
```

---

## Exporter Prometheus (`main.py`)

Interroge la Fronius Solar API à chaque scrape et expose les métriques sur `/metrics`.

### Lancement

```bash
uv run main.py --fronius-url http://192.168.1.10
```

### Options

| Option              | Défaut        | Description                                   |
| ------------------- | ------------- | --------------------------------------------- |
| `--fronius-url`     | *(obligatoire)* | URL de base (ex. `http://192.168.1.10`)    |
| `--listen-address`  | `0.0.0.0`     | Adresse d’écoute du serveur HTTP               |
| `--metrics-port`    | `9687`        | Port d’exposition des métriques                |
| `--timeout`         | `10`          | Timeout HTTP vers Fronius (secondes)          |
| `--prefix`          | `fronius_`    | Préfixe des noms de métriques Prometheus       |
| `--debug`           | —             | Active les logs de debug                       |

Variables d’environnement : `FRONIUS_URL`, `LISTEN_ADDR` (ex. `0.0.0.0:9687`), `FRONIUS_TIMEOUT`, `METRICS_PORT`.

### Exemple de métriques

```
fronius_site_power_photovoltaic_watts 1250.0
fronius_site_power_grid_watts -800.0
fronius_inverter_power_watts{inverter_id="1"} 1250.0
fronius_inverter_ac_power_watts{device_id="1"} 1250.0
fronius_scrape_duration_seconds 0.12
fronius_scrape_errors_total 0.0
```

### Intégration Prometheus

```yaml
# prometheus.yml
scrape_configs:
  - job_name: fronius-primo
    static_configs:
      - targets: ["localhost:9687"]
```

---

## CI/CD

Le pipeline GitHub Actions s’exécute à chaque push sur `master` et sur les pull requests :

1. **Lint** — `ruff check` + `ruff format --check`
2. **Tests** — `pytest` avec couverture (client, collector, metrics, main)
3. **Build & push** — construction de l’image Docker et push sur `ghcr.io` (désactivé sur les PR)

### Release manuelle

Le workflow **Release** (Actions → Release → Run workflow) permet de publier une version :

1. Saisir la version (ex. `1.0.0`)
2. Mise à jour de `pyproject.toml`, commit et tag (sans préfixe `v`)
3. Build et push de l’image avec les tags `1.0.0` et `latest`
4. Création d’une GitHub Release avec notes générées automatiquement

---

## Structure du projet

```
main.py            Exporter Prometheus (point d’entrée)
client.py          Client HTTP Fronius Solar API (v1)
collector.py       Collecteur Prometheus custom (thread-safe)
metrics.py         Helpers (safe_float)
pyproject.toml     Dépendances (prometheus-client, requests) + uv
Dockerfile         Image Docker basée sur uv
.github/
  workflows/
    ci.yml         CI : lint, tests, build & push Docker
    release.yml    Release manuelle : version, tag, image, GitHub Release
tests/
  test_*.py
```

---

## Références

- [Fronius Solar API (JSON)](https://www.fronius.com/en/solar-energy/installers-partners/technical-data/all-products/system-monitoring/open-interfaces/fronius-solar-api-json-)
- [ccremer/fronius-exporter](https://github.com/ccremer/fronius-exporter) (exporter Go)
- [pyfronius](https://github.com/nielstron/pyfronius) (client Python Solar API)

---

## Licence

Apache 2.0 — voir [LICENSE](LICENSE).
