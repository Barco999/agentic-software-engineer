# Optional Render deployment

No deployment or paid resource was provisioned. Docker build/run and Render deployment are supplied but not execution-verified here.

1. Push the reviewed project to your repository.
2. Create a Render web service using the Dockerfile. The default command starts Uvicorn on 0.0.0.0 and the configured PORT.
3. Set APP_BASE_URL to the service URL. Set model ID/key through environment secrets only if you need live local/operator workflows.
4. Keep workflow mutation CLI-only. Do not add unauthenticated start/approve endpoints.
5. For durable SQLite and checkpoint/workspace state, use a persistent mount (for example /data), DATABASE_URL=sqlite:////data/links.db and AGENT_DATA_DIR=/data/agentic. Persistent disks require a paid service; decide/provision this yourself.
6. Do not treat the supplied free ephemeral blueprint as durable production hosting. Free services may sleep; filesystem changes without persistent storage can be lost on restart/redeploy.
7. Verify /health, /docs and functional redirects after manual deployment. Back up all state before upgrades.

Dockerfile does not copy .env or use sensitive build arguments. .dockerignore excludes secrets, local runtime data and attachments.

Official references checked while implementing:

- https://render.com/docs/docker
- https://render.com/docs/disks
- https://render.com/docs/free

Provider/graph references:

- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://docs.langchain.com/oss/python/langgraph/graph-api
- https://ai.google.dev/api/generate-content
- https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
