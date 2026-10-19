# Genesis player experience v1

The Pages browser world now supports a complete local episode: create a lighthouse, approach its entrance, open the door, light its beacon, inspect the result, and return to the same state after reloading or importing a save.

## Player controls

- Free text remains the primary creation interface. Optional quick actions offer inspection, lighthouse creation, and returning to the first fire.
- The nearby interaction button follows actual distance and saved object state. `подойди к маяку`, `открой дверь`, `зажги маяк`, and `погаси маяк` also work as text commands; English equivalents are accepted.
- Approach walks toward the entrance. Manual movement, text focus, blur, and opening a drawer stop it. Accepted typed approach returns focus to the world.
- The lighthouse wall blocks both continuous and text movement. Opening its door permits entry through its entrance. This episode does not introduce general collision or interaction support for every historical structure recipe.
- A new lighthouse starts with a closed door and dark beacon. Historical lighthouses preserve their previously lit appearance until the player changes it.

## Interface and history

Command descriptions use actual execution results, including inspection data, movement distance, partial failure, and object state. Technical receipts remain available in collapsed details. History presents readable event descriptions and records time only when the event contains it.

The main view keeps the world, movement, command input, and optional goal visible. Camera controls, local save tools, and collapsed engineering diagnostics are in Settings. Open dialogs release movement and keep keyboard focus inside the dialog.

## Local save portability

The browser automatically saves on the current device. Settings can download a `janus.genesis.browser_export.v1` JSON file and preview a replacement before an explicit confirmation. No account or cross-device server synchronization is implied.

The importer checks the format, identity, size limit (2 MiB), finite coordinates, collection limits, Chronicle hashes, mutation provenance, and lighthouse state transitions. Provider binary data and download pointers are omitted. A single previous world is retained in the local backup key.

On confirmation, the runtime blocks new mutations, finishes queued Chronicle events, saves the completed previous world, and fences further old-session writes. The journal then backs up and replaces the local save. Success retains the fence until reload; failure restores the previous storage and releases it. The original birth event is preserved across a valid import.

## Verification

```text
python -m unittest tests.test_genesis_first_playable tests.test_genesis_player_feedback tests.test_genesis_browser_save
npm ci --prefix tests/browser
npx --prefix tests/browser playwright install chromium webkit
npm test --prefix tests/browser
npm run test:play --prefix tests/browser
```

The browser gates cover Chromium and WebKit at phone, tablet, landscape, and desktop sizes, both Pages entrypoints, a modeled keyboard viewport, the complete lighthouse episode, readable results and history, downloads, preview cancellation, invalid imports, replacement, and persistence. A physical iPhone keyboard still requires device testing.
