# CTFd Attack and Defense Plugin

## Installation

```sh
git clone https://github.com/splitline/CTFd-Attack-and-Defense-Plugin.git path/to/CTFd/plugins/awd
```

## API

- Endpoint: `http://YOUR_CTFd_HOST/plugins/awd/api/update`

```javascript
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
