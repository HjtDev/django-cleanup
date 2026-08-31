# Built with the REPO ROOT as context (playground/docker-compose.yml: `context: ..`), preserving
# the on-disk layout — /app/frontend (this app's own SDK, a workspace member) and
# /app/playground/frontend (also a workspace member) — so the repo-root npm WORKSPACE
# (package.json: "workspaces": ["frontend", "playground/frontend"]) resolves identically in and
# out of Docker. One hoisted node_modules is what dedupes react/@tanstack/react-query/
# @hjtdev/appkit between the SDK and this host — see docs/APP-DESIGN.md §12's "duplicate copy"
# hazard and ../../appkit/playground/frontend/Dockerfile's own version of this same comment.
#
# Unlike appkit's own playground Dockerfile (a package.json-only layer first, source copied
# after, for a leaner cache), this one copies frontend/'s FULL source before the one root-level
# `npm install` — frontend/package.json's own `prepare` script (`tsc -p tsconfig.build.json`)
# runs automatically as part of a workspace install, and needs tsconfig.build.json and src/
# already present. Copying package.json alone first (tried initially) failed the build outright:
# `error TS5058: The specified path does not exist: 'tsconfig.build.json'`. See FINDINGS.md.
FROM node:22-alpine
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json /app/
COPY frontend/ /app/frontend/
COPY playground/frontend/ /app/playground/frontend/
RUN npm install

WORKDIR /app/playground/frontend

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
