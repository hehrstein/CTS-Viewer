# CTS Strasbourg

Intégration Home Assistant pour les données temps réel de la Compagnie des Transports Strasbourgeois (CTS).

> Ce projet communautaire n'est pas affilié à la CTS. Il utilise l'API Open Data officielle de la CTS.

## Fonctionnalités

- Prochains trams pour les arrêts sélectionnés, avec ligne, direction, heure et temps restant.
- Attribut `board_rows` prêt à l'emploi pour créer un afficheur Lovelace avec le prochain et le suivant tram pour chaque ligne et direction.
- Informations trafic : travaux, perturbations et messages CTS pertinents pour l'arrêt.
- Places libres, capacité et taux d'occupation des parkings-relais (P+R).
- Actualisation configurable de 1 à 15 minutes.

## Installation avec HACS

1. Dans HACS, ouvrez **Intégrations** puis le menu ⋮ et choisissez **Dépôts personnalisés**.
2. Ajoutez `https://github.com/hehrstein/CTS-Viewer` avec la catégorie **Integration**.
3. Installez **CTS Strasbourg**, puis redémarrez Home Assistant.
4. Ouvrez **Paramètres → Appareils et services → Ajouter une intégration**, recherchez **CTS Strasbourg**, puis saisissez votre jeton personnel CTS.

Le jeton est stocké uniquement dans la configuration Home Assistant. Ne le placez jamais dans un fichier YAML, un commit ou une issue GitHub.

## Entités créées

Pour chaque arrêt de tram sélectionné :

- `Prochains trams` : premier départ à venir, avec les attributs détaillés.
- `Passages par direction` : résumé lisible des prochains passages.
- `Informations trafic` : message CTS actif, le cas échéant.

Pour chaque P+R sélectionné :

- `Places disponibles` : nombre de places libres, capacité, taux d'occupation et état d'ouverture.

## Données pour un afficheur de départs

Le capteur **Prochains trams** expose l'attribut `board_rows`. Chaque ligne représente une direction et contient les deux prochains passages.

```yaml
board_rows:
  - line: A
    direction: Illkirch Graffenstaden
    next:
      time: "13:32"
      minutes: 8
    following:
      time: "13:42"
      minutes: 18
```

Exemple de carte Markdown native :

```yaml
type: markdown
content: |
  {% set entity = 'sensor.cts_arret_tram_597_prochains_trams' %}
  {% set rows = state_attr(entity, 'board_rows') or [] %}
  | Ligne · destination | Prochain | Suivant |
  | :-- | --: | --: |
  {% for row in rows -%}
  | **{{ row['line'] }}**<br>{{ row['direction'] }} | **{{ (row['next'] or {}).get('minutes', '—') }} min**<br>{{ (row['next'] or {}).get('time', '') }} | **{{ (row['following'] or {}).get('minutes', '—') }} min**<br>{{ (row['following'] or {}).get('time', '') }} |
  {% endfor %}
```

## Développement

La structure HACS est la suivante :

```text
custom_components/cts_strasbourg/
```

Exécutez les vérifications GitHub Actions HACS et Hassfest avant chaque publication.

## Source de données

- [API Open Data CTS](https://api.cts-strasbourg.eu/)
- SIRI Stop Monitoring pour les départs tram
- SIRI General Message pour les informations trafic
- Park and Ride pour les P+R
