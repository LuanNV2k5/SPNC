import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";

// docs/46 D5: Monaco is bundled, never loaded from a CDN (CSP script-src 'self').
// C++ and Python need only the generic editor worker (no language services).
self.MonacoEnvironment = { getWorker: () => new editorWorker() };
loader.config({ monaco });
