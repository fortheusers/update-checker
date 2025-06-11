## update-checker
Github bot that checks for changes of hbas appstore packages and creates PRs against the metadata repo ([switch-hbas-repo](https://github.com/fortheusers/switch-hbas-repo))

### Running
Edit `.env.template` with GH API key and target repo, and then run the following to start the main update checking loop:

```
mv .env.template .env
docker compose build
docker compose run update-checker
```
