# Front-end tests

These drive the real built page (`backend/static/index.html`) in a DOM, with
stylesheets applied. That matters: the worst bug found here was a CSS
`display: flex` rule silently overriding the HTML `hidden` attribute, which no
amount of reading the JavaScript would have revealed.

```bash
npm install jsdom
node tests-frontend/ui.test.js
```

48 checks covering the opening state, the paste-to-HTML path, the Code and
Preview toggle, generating and scoring a paper, copy and reset, input
validation, and how a server error surfaces to the reader.
