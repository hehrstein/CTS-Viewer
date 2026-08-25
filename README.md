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

## Obtenir une clé API CTS

L’intégration nécessite un token d’accès à l’API Open Data de la CTS.

Pour obtenir ce token, contactez la CTS à l’adresse
[open-data@cts-strasbourg.fr](mailto:open-data@cts-strasbourg.fr)
afin de demander l’accès au portail Open Data.

Une fois l’accès accordé, récupérez votre token depuis ce portail, puis
saisissez-le lors de la configuration de l’intégration dans Home Assistant.

> Ne partagez jamais votre token et ne l’ajoutez pas à un dépôt GitHub.
> S’il est exposé, demandez sa révocation et générez-en un nouveau.

Pour plus d’informations, consultez la [page Open Data de la CTS](https://www.cts-strasbourg.eu/fr/open-data/).

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

  _Données issues de CTS — API Open Data CTS. Dernière mise à jour : {{ state_attr(entity, 'recorded_at') or 'non communiquée' }}._
```

## Licence et attribution des données CTS

Le code source de cette intégration est distribué sous licence MIT. Cette licence ne s’applique qu’au code et à sa documentation : elle ne confère aucun droit sur les données, les marques ou les logos de la CTS.

Les données récupérées au moment de l’utilisation restent soumises à la **Licence de réutilisation des informations publiques CTS** acceptée lors de l’accès au portail Open Data. Cette licence autorise la réutilisation, y compris commerciale, sous réserve notamment de :

- mentionner la source CTS et la date de dernière mise à jour ;
- ne pas altérer les données ni en dénaturer le sens ; les commentaires ou enrichissements doivent être clairement distingués des informations CTS ;
- ne pas reproduire les marques ou logos CTS ;
- ne pas présenter les données CTS comme étant couvertes par la licence MIT du projet.

Toute carte, automatisation ou interface qui affiche ou retransmet ces données doit faire apparaître, de manière lisible, une mention telle que :

> Données issues de CTS — API Open Data CTS. Dernière mise à jour : `<horodatage fourni par l’API>`.

Pour les départs tram, l’horodatage est disponible dans l’attribut `recorded_at`. Pour les P+R, utilisez l’attribut `last_update`. Chaque installation doit utiliser son propre token Open Data CTS ; l’intégration ne contient ni token ni données CTS préchargées.

## Fraîcheur et cache des données

Chaque entité expose les mêmes attributs de suivi :

- `attribution` et `data_source` : source officielle des données ;
- `data_updated_at` : moment où la réponse a été obtenue auprès de la CTS ;
- `data_cache_expires_at` : moment avant lequel la réponse reste réutilisable ;
- `data_from_cache` : indique que toutes les données affichées par l’entité proviennent du cache local.

L’intégration respecte l’en-tête HTTP `Cache-Control` fourni par l’API CTS. En son absence, elle utilise les métadonnées SIRI `ValidUntil` et `ShortestPossibleCycle` lorsqu’elles sont disponibles. Elle n’interroge les P+R que si au moins un P+R est configuré, et les départs/messages trafic que si au moins un arrêt tram est configuré.

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
