const express = require('express');
const next = require('next');

const dev = process.env.NODE_ENV !== 'production';
const app = next({ dev });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  const server = express();

  // Custom Express gateway routes could go here
  server.get('/health', (req, res) => res.send('OK'));

  // Catch-all: hand everything else to Next. Use middleware (not a '*' route) —
  // Express 5 / path-to-regexp v8 rejects the bare '*' path string.
  server.use((req, res) => {
    return handle(req, res);
  });

  const port = process.env.PORT || 3000;
  server.listen(port, (err) => {
    if (err) throw err;
    console.log(`> Ready on http://localhost:${port}`);
  });
});
