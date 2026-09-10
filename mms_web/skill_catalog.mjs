import { readFileSync, realpathSync } from 'node:fs';
import { dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
const request = JSON.parse(readFileSync(0, 'utf8'));
const { loadSkills } = await import(pathToFileURL(request.module).href);
const result = loadSkills({cwd: request.cwd, agentDir: request.agentDir, includeDefaults: false, skillPaths: request.paths});
process.stdout.write(JSON.stringify({skills:result.skills.map(s => ({name:s.name, description:s.description, filePath:realpathSync(s.filePath), baseDir:dirname(realpathSync(s.filePath)), manualOnly:s.disableModelInvocation})), diagnostics:result.diagnostics.map(d=>({message:d.message}))}));
