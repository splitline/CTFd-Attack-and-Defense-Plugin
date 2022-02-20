# CTFd Attack and Defense Plugin

## Installation


## API

- Endpoint: `http://YOUR_CTFd_HOST/plugins/awd/api/update`

```json
{
    "id": <challenge-id>,
    "token": "<token>", // you'll see it after you create the challenge
    "attacks": {
        <team-id>, <points>,
        <team-id>: <points>
    },
    "defenses": [ <team-id>, <team-id>, ... ]
}
```
