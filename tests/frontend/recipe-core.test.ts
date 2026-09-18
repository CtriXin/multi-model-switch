import test from "node:test";
import assert from "node:assert/strict";
import { parseRecipe, renderRecipe, prepareExport, scrubSharedText, variableNames, modelRequirementIssues, requiredSkillMatches } from "../../apps/mms-web/src/recipe-core.ts";
import type { Recipe } from "../../apps/mms-web/src/recipe-core.ts";
const sample = (overrides = {}): Recipe => ({ format: "mms-work-recipe-v2", title: "整理资料", prompt: "整理 {{file}}，主题 {{topic}}。", preferredModel: "gpt-5", planning: false, examples: { input: "主题：{{topic}}", output: "一段中文结论" }, requiredSkills: ["writing-guide"], modelRequirements: { image: false, reasoning: true }, variables: ["file", "topic"], ...overrides });

test("v2 round trip and v1 plain text compatibility", () => {
  const value = sample();
  assert.deepEqual(parseRecipe(prepareExport(value).json), value);
  const legacy = parseRecipe(JSON.stringify({format:"mms-work-recipe-v1", title:"old", prompt:"literal {{legacy}}", planning:true}));
  assert.equal(renderRecipe(legacy, {}), "literal {{legacy}}");
  assert.deepEqual(legacy.requiredSkills, []);
  assert.equal(legacy.planning, true);
});
test("malformed roots, versions and typed requirements fail without weakening", () => {
  for (const value of [[], null, {format:"mms-work-recipe-v3"}, sample({planning:"true"}), sample({requiredSkills:"writing-guide"}), sample({modelRequirements:{image:"true"}}), sample({examples:[]}), sample({prompt:" "})]) assert.throws(() => parseRecipe(JSON.stringify(value)));
  assert.throws(() => parseRecipe("x".repeat(128001)));
  assert.throws(() => parseRecipe(JSON.stringify(sample({prompt:"中".repeat(45000)}))));
  assert.throws(() => parseRecipe(JSON.stringify(sample({requiredSkills:Array.from({length:21},(_,i)=>`s${i}`)}))));
});
test("variables require exact distinct declarations, reject reserved names", () => {
  for (const value of [sample({variables:["file"]}),sample({variables:["file","topic","extra"]}),sample({variables:["file","file","topic"]}),sample({prompt:"{{constructor}}",variables:["constructor"]}),sample({prompt:"{{bad name}}",variables:["bad name"]})]) assert.throws(()=>parseRecipe(JSON.stringify(value)));
  assert.throws(()=>renderRecipe(sample(), {file:" ",topic:"中文"}));
  assert.deepEqual(variableNames("{{x}} {{x}}", "{{x}} {{y}}"), ["x","y"]);
});
test("substitution is one literal pass; examples stay explicitly examples", () => {
  const literal = "$& $1 \\ \n <script>literal</script> {{topic}}";
  const result = renderRecipe(sample(), {file:literal,topic:"中文"});
  assert.ok(result.includes(literal));
  assert.ok(result.includes("主题 中文"));
  assert.ok(result.includes("预期成果示例（供参考，并非已完成的结果）"));
  assert.throws(()=>renderRecipe(sample(), {file:"x".repeat(50000),topic:"y"}));
});
test("privacy scrub covers credentials, assignments, URLs and machine paths", () => {
  const sensitive = [
    "sk-abcdefghijklmnopqrstuv", "Bearer SECRET_BEARER_123", "export PRIVATE_SETTING=secret-setting", "API_TOKEN=secret-token",
    "api_key: secret-key", 'password="hidden-word"', "https://user:pass@example.test/private", "https://example.test/?token=secret-query",
    "/Users/private-owner/file.md", "/home/private-owner/file.md", "/tmp/private-input.csv", "~/private/path", "C:\\PrivateOwner\\data.csv", "\\\\server\\private\\data.csv", "file:///Users/private-owner/file.md",
    "-----BEGIN PRIVATE KEY-----\nPRIVATE_BLOCK\n-----END PRIVATE KEY-----"
  ];
  for (const original of sensitive) {
    const value = scrubSharedText(original);
    assert.ok(value.removed > 0, original);
    assert.notEqual(value.text, original, original);
    assert.equal(scrubSharedText(value.text).text, value.text, "idempotent: " + original);
  }
  const plain = "https://example.test/docs?a=1 文档 ./docs/input.md src/file.ts x / y 和 a/b";
  assert.equal(scrubSharedText(plain).text, plain);
});
test("export is a whitelist and checks every field and filename again", () => {
  const secret = "sk-abcdefghijklmnopqrstuv";
  const result = prepareExport(sample({ title:secret, prompt:"/Users/private-owner/input.md "+secret, preferredModel:secret, examples:{input:"PASSWORD=NEVER_EXPORT", output:secret}, history:"PRIVATE_HISTORY", contextUsage:{cwd:"PRIVATE_CWD"}, env:{API_KEY:"PRIVATE_ENV"}, attachments:[{data:"PRIVATE_BYTES"}], variables:[] }));
  for (const marker of [secret,"private-owner","NEVER_EXPORT","PRIVATE_HISTORY","PRIVATE_CWD","PRIVATE_ENV","PRIVATE_BYTES"]) {
    assert.ok(!result.json.includes(marker)); assert.ok(!result.filename.includes(marker));
  }
  assert.deepEqual(Object.keys(JSON.parse(result.json)).sort(),["format","title","prompt","preferredModel","planning","examples","requiredSkills","modelRequirements","variables"].sort());
  assert.equal(prepareExport(result.recipe).json,result.json);
  assert.ok(!prepareExport({...result.recipe,prompt:secret}).json.includes(secret));
});
test("model facts must positively satisfy requirements", () => {
  assert.ok(modelRequirementIssues(sample(),undefined).length);
  assert.ok(modelRequirementIssues(sample(),{}).length);
  assert.ok(modelRequirementIssues(sample(),{reasoning:false}).length);
  assert.deepEqual(modelRequirementIssues(sample(),{reasoning:true}),[]);
  const image=sample({modelRequirements:{image:true,reasoning:false}});
  assert.ok(modelRequirementIssues(image,{input:["text"]}).length);
  assert.deepEqual(modelRequirementIssues(image,{input:["text","image"]}),[]);
});
test("only unique current-project and actually selected skill IDs satisfy names", () => {
  const skills=[{id:"local-a",name:"writing-guide"}];
  assert.deepEqual(requiredSkillMatches(["writing-guide"],skills),{ids:["local-a"],issues:[]});
  assert.ok(requiredSkillMatches(["writing-guide"],[],["local-a"]).issues.length);
  assert.ok(requiredSkillMatches(["writing-guide"],skills,[]).issues.length);
  assert.ok(requiredSkillMatches(["writing-guide"],[...skills,{id:"other",name:"writing-guide"}]).issues.length);
  assert.deepEqual(requiredSkillMatches(["writing-guide"],skills,["local-a"]).issues,[]);
});

test("quoted paths with spaces and secret-like names cannot leak through metadata", () => {
  for (const value of ['"C:\\Users\\Private Owner\\file.csv"', '`/Users/Private Owner/file.md`']) {
    const result = scrubSharedText(value);
    assert.ok(!result.text.includes("Private Owner"));
  }
  assert.throws(()=>prepareExport(sample({requiredSkills:["sk-abcdefghijklmnopqrstuv"]})));
  assert.throws(()=>prepareExport(sample({prompt:"{{sk_abcdefghijklmnopqrstuv}}",variables:["sk_abcdefghijklmnopqrstuv"]})));
});

test("quoted credential fields and escaped quote values are fully scrubbed", () => {
  for (const input of ['{"api_key":"REVIEW_LEAK"}', "{'access_token': 'REVIEW_LEAK'}", String.raw`{"password":"prefix\"REVIEW_LEAK"}`, '"client_secret": "REVIEW_LEAK"']) {
    assert.ok(!prepareExport(sample({prompt:input,variables:[]})).json.includes('REVIEW_LEAK'),input);
  }
});
test("legacy literal variables survive normalized draft refresh and export", () => {
  const legacy=parseRecipe(JSON.stringify({format:'mms-work-recipe-v1',prompt:'literal {{legacy}} and {{bad name}}'}));
  const restored=parseRecipe(JSON.stringify(legacy));
  assert.equal(renderRecipe(restored,{}),'literal {{legacy}} and {{bad name}}');
  assert.equal(renderRecipe(parseRecipe(prepareExport(restored).json),{}),renderRecipe(legacy,{}));
});
test("unknown requirements and coerced version cannot silently weaken requirements", () => {
  for(const value of [sample({format:['mms-work-recipe-v2']}),sample({modelRequirements:{image:false,video:true}}),sample({interpolation:'unknown'})]) assert.throws(()=>parseRecipe(JSON.stringify(value)));
});
test("final pretty export must pass the exact same byte limit as import", () => {
  let edge: Recipe | undefined;
  for(let n=42000;n<42700;n++) {
    const value=sample({prompt:'中'.repeat(n),examples:{input:'',output:''},variables:[],requiredSkills:[]});
    if(new TextEncoder().encode(JSON.stringify(value)).length<=128000 && new TextEncoder().encode(JSON.stringify(value,null,2)).length>128000) {edge=value;break;}
  }
  assert.ok(edge, 'must exercise compact-versus-pretty boundary');
  assert.throws(()=>prepareExport(edge!));
  const smaller=prepareExport({...edge!,prompt:edge!.prompt.slice(0,-100)});
  assert.deepEqual(parseRecipe(smaller.json),smaller.recipe);
});
