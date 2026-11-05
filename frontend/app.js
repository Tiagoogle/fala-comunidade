// Escuta+ — PWA do agente de campo (spec §8.6: modo offline é requisito de primeira classe).
// Sem build, sem dependências. A fila offline fica no IndexedDB, cifrada com AES-GCM
// (chave não exportável gerada no próprio aparelho via WebCrypto).

const API = location.origin + (window.ESCUTA_API || "");
const $ = (s) => document.querySelector(s);
const chave = () => { try { return localStorage.getItem("escuta.chave") || ""; } catch { return ""; } };
const cab = () => ({ "Content-Type": "application/json", "X-Chave-Acesso": chave() });

// ---------------------------------------------------------------- emergência no aparelho
// Mesmo sem rede e sem servidor, o agente vê na hora os números de emergência.
const EMERG = [/\bacidente\b/, /\bsangr/, /\bferid[oa]/, /\bdesmai/, /\bpres[oa] (embaixo|debaixo|sob)/, /\bsoterrad/, /\bfogo\b/, /\bincendio/,
  /\bexplos/, /\bafog/, /\bdesab/, /\bdesmoron/, /\bdeslizament/, /\bbarragem (rompeu|rompendo|estourou|vazando)/, /\bsirene/, /\benchente\b/,
  /\bameac\w* de morte/, /\barmad[oa]/, /\btiro/, /\bagred/, /\bviolencia domestica/, /\btombou\b/, /\bcapotou\b/, /\batropel/, /\bsocorro\b/,
  /\bintoxica/, /\bfumaca (saindo|preta|subindo|forte)/, /\bmuita fumaca\b/];
const normalizar = (t) => (t || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
const pareceEmergencia = (t) => EMERG.some((r) => r.test(normalizar(t)));
function alertaEmergencia(on) { $("#alerta-emergencia").hidden = !on; }

// ---------------------------------------------------------------- IndexedDB + cifra
const idb = new Promise((ok, erro) => {
  const req = indexedDB.open("escuta", 1);
  req.onupgradeneeded = () => { req.result.createObjectStore("fila", { keyPath: "id" }); req.result.createObjectStore("cfg"); };
  req.onsuccess = () => ok(req.result); req.onerror = () => erro(req.error);
});
async function tx(store, modo, fn) {
  const db = await idb;
  return new Promise((ok, erro) => { const t = db.transaction(store, modo); const r = fn(t.objectStore(store)); t.oncomplete = () => ok(r?.result); t.onerror = () => erro(t.error); });
}
async function chaveLocal() {
  let k = await tx("cfg", "readonly", (s) => s.get("aes"));
  if (!k) { k = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]); await tx("cfg", "readwrite", (s) => s.put(k, "aes")); }
  return k;
}
async function cifrar(obj) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const dados = new TextEncoder().encode(JSON.stringify(obj));
  return { iv, ct: await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await chaveLocal(), dados) };
}
async function decifrar({ iv, ct }) {
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, await chaveLocal(), ct);
  return JSON.parse(new TextDecoder().decode(pt));
}
const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : Date.now() + "-" + Math.random().toString(16).slice(2));
const codigo6 = () => String(crypto.getRandomValues(new Uint32Array(1))[0] % 1e6).padStart(6, "0");
const fmtCodigo = (c) => c ? c.replace(/(\d{3})(\d{3})/, "$1-$2") : "";
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------------------------------------------------------------- conexão e abas
async function checarConexao() {
  const el = $("#conexao");
  try { const r = await fetch(API + "/saude", { cache: "no-store" }); const j = await r.json(); el.textContent = `online · IA: ${j.provedor_llm}`; el.className = "pilula on"; return true; }
  catch { el.textContent = "sem conexão — registros ficam no aparelho"; el.className = "pilula off"; return false; }
}
window.addEventListener("online", () => { checarConexao(); sincronizar(); });
window.addEventListener("offline", checarConexao);

document.querySelectorAll(".abas button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".abas button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
  document.querySelectorAll(".aba").forEach((s) => (s.hidden = s.id !== "aba-" + b.dataset.aba));
  if (b.dataset.aba === "fila") carregarFila();
  if (b.dataset.aba === "gov") carregarChaves();
}));
$("#fonte").addEventListener("click", (e) => {
  const on = document.documentElement.classList.toggle("grande");
  e.currentTarget.setAttribute("aria-pressed", String(on));
  try { localStorage.setItem("escuta.fonte", on ? "1" : ""); } catch {}
});
try { if (localStorage.getItem("escuta.fonte")) document.documentElement.classList.add("grande"); } catch {}

async function api(caminho, opts = {}) {
  const r = await fetch(API + caminho, { ...opts, headers: { ...cab(), ...(opts.headers || {}) } });
  const corpo = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error(typeof corpo === "object" ? (typeof corpo.detail === "string" ? corpo.detail : JSON.stringify(corpo.detail)) : corpo);
  return corpo;
}

// ---------------------------------------------------------------- conversa
let sessao = null;
function bolha(autor, texto, extra = {}) {
  const d = document.createElement("div");
  d.className = `msg ${autor}` + (extra.emergencia ? " emerg" : "");
  d.textContent = texto;
  if (extra.protocolo && extra.codigo) {
    const m = document.createElement("span"); m.className = "meta";
    m.textContent = `Protocolo ${extra.protocolo} · código ${fmtCodigo(extra.codigo)} — anote para a pessoa`;
    d.appendChild(m);
  }
  $("#chat").appendChild(d); $("#chat").scrollTop = $("#chat").scrollHeight;
}
function opcoes(lista) {
  const box = $("#opcoes"); box.innerHTML = "";
  for (const o of lista || []) {
    const b = document.createElement("button"); b.type = "button"; b.textContent = o;
    b.onclick = () => { if (o.startsWith("Ligar ")) { location.href = "tel:" + o.split(" ")[1]; return; } enviar(o); };
    box.appendChild(b);
  }
}
async function novaConversa() {
  $("#chat").innerHTML = ""; opcoes([]);
  try {
    const r = await api("/conversas", { method: "POST", body: JSON.stringify({ canal: "app_campo" }) });
    sessao = r.id_sessao; try { localStorage.setItem("escuta.sessao", sessao); } catch {}
    bolha("agente", r.texto); opcoes(r.opcoes);
  } catch (e) { bolha("agente", "Sem conexão com o servidor. Use a aba “Registro offline”: o registro fica guardado no aparelho e é enviado depois. (" + e.message + ")"); }
}
async function retomar() {
  try { sessao = localStorage.getItem("escuta.sessao"); } catch { sessao = null; }
  if (!sessao) return novaConversa();
  try {
    const h = await api(`/conversas/${sessao}/historico`);
    for (const t of h.turnos) bolha(t.autor, t.texto);
    const r = await api(`/conversas/${sessao}`);
    bolha("agente", h.turnos.length ? "Continuando de onde paramos — nada do que foi dito se perdeu." : r.texto);
    opcoes(r.opcoes);
  } catch { novaConversa(); }
}
const pendentesChat = [];
async function enviar(texto) {
  if (!texto.trim()) return;
  bolha("usuario", texto); opcoes([]);
  alertaEmergencia(pareceEmergencia(texto));
  const msg = { texto, client_msg_id: uuid() };
  try {
    const r = await api(`/conversas/${sessao}/mensagens`, { method: "POST", body: JSON.stringify(msg) });
    bolha("agente", r.texto, { emergencia: r.emergencia, protocolo: r.protocolo, codigo: r.codigo_consulta });
    alertaEmergencia(r.emergencia || pareceEmergencia(texto));
    opcoes(r.opcoes);
  } catch (e) {
    pendentesChat.push(msg);
    bolha("agente", "A conexão caiu. Sua mensagem está guardada e será reenviada quando a rede voltar — nada se perde." +
      (pareceEmergencia(texto) ? " Se houver risco agora, ligue: SAMU 192, Bombeiros 193, Polícia 190." : ""));
  }
}
async function reenviarChat() {
  while (pendentesChat.length && sessao) {
    const m = pendentesChat[0];
    try { const r = await api(`/conversas/${sessao}/mensagens`, { method: "POST", body: JSON.stringify(m) }); pendentesChat.shift();
      bolha("agente", "Continuando de onde paramos: " + r.texto, { emergencia: r.emergencia, protocolo: r.protocolo, codigo: r.codigo_consulta }); opcoes(r.opcoes); }
    catch { break; }
  }
}
window.addEventListener("online", reenviarChat);
$("#form-chat").addEventListener("submit", (e) => { e.preventDefault(); const t = $("#entrada").value; $("#entrada").value = ""; enviar(t); });
$("#entrada").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#form-chat").requestSubmit(); } });
$("#nova-conversa").addEventListener("click", novaConversa);
$("#pedir-pessoa").addEventListener("click", () => enviar("Quero falar com uma pessoa."));
$("#anexo-chat").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (!f) return;
  const fd = new FormData(); fd.append("arquivo", f, f.name);
  const descricao = prompt("Quer contar rapidamente o que o arquivo mostra? (opcional)") || "";
  if (descricao) fd.append("descricao", descricao);
  try {
    const r = await fetch(`${API}/conversas/${sessao}/anexos`, { method: "POST", body: fd, headers: { "X-Chave-Acesso": chave() } });
    const j = await r.json();
    bolha("agente", r.ok ? j.mensagem : j.detail);
  } catch { bolha("agente", "Sem conexão: o arquivo não foi enviado. Tente de novo quando a rede voltar."); }
  finally { e.target.value = ""; }
});

// ---------------------------------------------------------------- registro offline
document.querySelectorAll('input[name="modo"]').forEach((r) => r.addEventListener("change", () => {
  $("#campos-id").hidden = document.querySelector('input[name="modo"]:checked').value === "anonimo";
}));
$("#r-relato").addEventListener("input", (e) => alertaEmergencia(pareceEmergencia(e.target.value)));
$("#r-transcricao").addEventListener("input", (e) => alertaEmergencia(pareceEmergencia(e.target.value)));

let gravador = null, pedacos = [], audioBlob = null;
$("#gravar").addEventListener("click", async () => {
  if (gravador?.state === "recording") { gravador.stop(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    gravador = new MediaRecorder(stream); pedacos = [];
    gravador.ondataavailable = (e) => pedacos.push(e.data);
    gravador.onstop = () => { audioBlob = new Blob(pedacos, { type: gravador.mimeType || "audio/webm" }); $("#previa").src = URL.createObjectURL(audioBlob); $("#previa").hidden = false;
      $("#gravar").textContent = "● Gravar de novo"; $("#gravando").textContent = "Áudio guardado. O original é a versão oficial da fala."; stream.getTracks().forEach((t) => t.stop()); };
    gravador.start(); $("#gravar").textContent = "■ Parar"; $("#gravando").textContent = "Gravando…";
  } catch { $("#gravando").textContent = "Microfone indisponível — registre por texto."; }
});

$("#form-registro").addEventListener("submit", async (e) => {
  e.preventDefault();
  const relato = $("#r-relato").value.trim(), transc = $("#r-transcricao").value.trim(), ok = $("#r-transcricao-ok").checked;
  if (!relato && !audioBlob && !transc) { alert("Escreva o relato ou grave um áudio."); return; }
  if (!$("#r-consent").checked) { alert("Sem o de acordo da pessoa, o registro não é guardado. Ofereça o atendimento presencial/ouvidoria."); return; }
  const modo = document.querySelector('input[name="modo"]:checked').value;
  const audio = !!audioBlob && !relato;
  const codigo = codigo6();
  const item = {
    id: uuid(), criado_em: new Date().toISOString(), codigo, estado: "pendente",
    corpo: {
      relato: audio ? (ok && transc ? transc : "[áudio gravado em campo — transcrição pendente]") : [relato, transc && ok ? `[transcrição] ${transc}` : ""].filter(Boolean).join("\n"),
      canal_origem: "app_campo", localidade: $("#r-local").value || null, desde_quando: $("#r-desde").value || null,
      modo_identificacao: modo, nome: modo !== "anonimo" ? $("#r-nome").value || null : null, contato: modo !== "anonimo" ? $("#r-contato").value || null : null,
      consentimento_tratamento: true, consentimento_notificacoes: $("#r-notif").checked, meio_consentimento: "presencial",
      demanda_coletiva: $("#r-coletiva").checked, pedido_pessoa: $("#r-pessoa").checked,
      recursos_acessibilidade: $("#r-acess").value ? $("#r-acess").value.split(",").map((s) => s.trim()).filter(Boolean) : [],
      original_tipo: audio ? "audio" : "texto", transcricao_pendente: audio && !(ok && transc), codigo_consulta: codigo,
    },
  };
  item.corpo.client_msg_id = item.id;
  const audioBuf = audioBlob ? { tipo: audioBlob.type, dados: Array.from(new Uint8Array(await audioBlob.arrayBuffer())) } : null;
  const selado = await cifrar({ corpo: item.corpo, audio: audioBuf });
  await tx("fila", "readwrite", (s) => s.put({ id: item.id, criado_em: item.criado_em, estado: "pendente", emergencia: pareceEmergencia(item.corpo.relato), selado }));
  const em = pareceEmergencia(item.corpo.relato);
  $("#recibo").hidden = false;
  $("#recibo").innerHTML = `<p>Registro guardado neste aparelho${em ? " <strong>com marcador de possível emergência</strong>" : ""}.</p>
    <p>Código de consulta para a pessoa: <span class="grande">${fmtCodigo(codigo)}</span></p>
    <p>O número de protocolo é gerado quando o aparelho sincronizar${navigator.onLine ? " (agora)" : " — a pessoa recebe na próxima visita ou por mensagem"}. O prazo-alvo é um alvo interno, não uma promessa.</p>`;
  e.target.reset(); audioBlob = null; $("#previa").hidden = true; $("#campos-id").hidden = true; $("#gravar").textContent = "● Gravar áudio"; $("#gravando").textContent = "";
  await listarLocal(); sincronizar();
});

async function listarLocal() {
  const itens = (await tx("fila", "readonly", (s) => s.getAll())) || [];
  const pend = itens.filter((i) => i.estado !== "enviado").length;
  $("#pendentes").hidden = !pend; $("#pendentes").textContent = `${pend} aguardando envio`;
  $("#lista-local").innerHTML = itens.sort((a, b) => b.criado_em.localeCompare(a.criado_em)).map((i) =>
    `<li><span>${new Date(i.criado_em).toLocaleString("pt-BR")}${i.emergencia ? " · <strong>emergência</strong>" : ""}</span>
     <span>${i.estado === "enviado" ? `protocolo <strong>${esc(i.protocolo)}</strong>` : "aguardando conexão"}</span></li>`).join("") || "<li>Nenhum registro.</li>";
}

let sincronizando = false;
async function sincronizar() {
  if (sincronizando || !chave()) return; sincronizando = true;
  try {
    const itens = ((await tx("fila", "readonly", (s) => s.getAll())) || []).filter((i) => i.estado !== "enviado");
    // emergências primeiro
    itens.sort((a, b) => Number(b.emergencia) - Number(a.emergencia));
    for (const i of itens) {
      const { corpo, audio } = await decifrar(i.selado);
      let r;
      try { r = await api("/manifestacoes", { method: "POST", body: JSON.stringify(corpo) }); } catch { break; } // idempotente por client_msg_id
      if (audio) {
        const fd = new FormData(); fd.append("arquivo", new Blob([new Uint8Array(audio.dados)], { type: audio.tipo.split(";")[0] }), "relato-audio");
        fd.append("descricao", "áudio original do relato (gravado em campo)");
        try { await fetch(`${API}/manifestacoes/${r.id}/anexos`, { method: "POST", body: fd, headers: { "X-Chave-Acesso": chave() } }); } catch { break; }
      }
      // após envio, o aparelho guarda só o protocolo — o conteúdo sai do dispositivo (minimização)
      await tx("fila", "readwrite", (s) => s.put({ id: i.id, criado_em: i.criado_em, estado: "enviado", protocolo: r.protocolo, emergencia: i.emergencia }));
    }
  } finally { sincronizando = false; listarLocal(); }
}
$("#sincronizar").addEventListener("click", sincronizar);

// ---------------------------------------------------------------- fila e caso
async function carregarFila() {
  const ul = $("#lista-fila"); ul.innerHTML = "<li>Carregando…</li>";
  try {
    const itens = await api("/fila");
    ul.innerHTML = itens.map((i) => `<li><span><span class="prio ${esc(i.prioridade)}">${esc(i.prioridade)}</span> ${esc(i.motivo.replace("_", " "))} · ${esc(i.contexto)}
      ${i.rota === "sigilosa" ? " · <strong>sigilosa</strong>" : ""}</span>
      <span>${i.responsavel ? `com ${esc(i.responsavel)} <button class="botao-sec" data-resolver="${i.id}">Resolver</button>` : `<button class="botao-sec" data-assumir="${i.id}">Assumir</button>`}
      ${i.id_manifestacao && i.motivo !== "direito_titular" ? `<button class="botao-sec" data-caso="${i.id_manifestacao}">Abrir caso</button>` : ""}</span></li>`).join("") || "<li>Fila vazia.</li>";
    ul.querySelectorAll("[data-resolver]").forEach((b) => b.onclick = async () => {
      const resolucao = prompt("O que foi feito? (fica registrado na auditoria)"); if (!resolucao) return;
      try { await api(`/fila/${b.dataset.resolver}/resolver`, { method: "POST", body: JSON.stringify({ resolucao }) }); } catch (e) { alert(e.message); }
      carregarFila();
    });
    ul.querySelectorAll("[data-assumir]").forEach((b) => b.onclick = async () => { await api(`/fila/${b.dataset.assumir}/assumir`, { method: "POST" }); carregarFila(); });
    ul.querySelectorAll("[data-caso]").forEach((b) => b.onclick = () => abrirCaso(b.dataset.caso));
  } catch (e) { ul.innerHTML = `<li>${esc(e.message)}</li>`; }
}
$("#atualizar-fila").addEventListener("click", carregarFila);

async function abrirCaso(id) {
  const box = $("#caso"); box.hidden = false; box.textContent = "Carregando…";
  try {
    const c = await api(`/manifestacoes/${id}`);
    const t = c.triagem_sugerida;
    box.innerHTML = `<h3>${esc(c.protocolo)} ${c.emergencia ? '<span class="prio P1">EMERGÊNCIA</span>' : ""} ${c.rota === "sigilosa" ? "· rota sigilosa" : ""}</h3>
      <p><strong>Original (imutável):</strong></p><blockquote>${esc(c.conteudo_original)}</blockquote>
      ${c.adendos.map((a) => `<p class="ia">Adendo v${a.versao} (${esc(a.tipo)}) por ${esc(a.autor)}:</p><blockquote>${esc(a.conteudo)}</blockquote>`).join("")}
      <p class="ia">Resumo ${c.resumo_confirmado ? "confirmado pela pessoa" : "NÃO confirmado"}: ${esc(c.resumo_ia)}</p>
      <p><strong>Triagem sugerida</strong> <span class="ia">(${esc(t.gerada_por)})</span>: ${esc(t.tipo)} · ${esc(t.tema)} · <span class="prio ${esc(t.prioridade)}">${esc(t.prioridade)}</span> · confiança ${esc(t.confianca)} · área sugerida ${esc(t.area)}</p>
      <p class="ia">Justificativa: ${esc(t.justificativa)}</p>
      <p>Local: ${esc(c.localidade || "—")} · Desde: ${esc(c.desde_quando || "—")} · Identificação: ${esc(c.modo_identificacao)} · Status: ${esc(c.status)}
      ${c.prioridade_validada ? ` · <strong>Prioridade validada: ${esc(c.prioridade_validada)}</strong>` : ""}</p>
      <form id="f-aval" class="grade"><fieldset><legend>Validação humana (justificativa obrigatória)</legend>
        <label>Resultado <select id="a-res"><option value="confirmada">Confirmar sugestão</option><option value="reclassificada">Reclassificar</option><option value="sensivel">Marcar como sensível (rota sigilosa)</option><option value="devolvida">Devolver (falta informação)</option><option value="recusada">Recusar (com motivo)</option></select></label>
        <label>Nova prioridade (se reclassificar) <select id="a-prio"><option value="">—</option><option>P1</option><option>P2</option><option>P3</option><option>P4</option></select></label>
        <label>Justificativa <textarea id="a-just" required></textarea></label>
        <button class="botao">Registrar avaliação</button></fieldset></form>
      <form id="f-enc" class="grade"><fieldset><legend>Encaminhar (após validação)</legend>
        <label>Área <input id="e-area" value="${esc(t.area || "")}" required></label>
        <label>Responsável (pessoa/função) <input id="e-resp" required></label>
        <button class="botao">Encaminhar</button></fieldset></form>
      <p id="caso-msg" role="status" aria-live="polite"></p>`;
    $("#f-aval").onsubmit = async (e) => { e.preventDefault();
      try { await api(`/manifestacoes/${id}/avaliacoes`, { method: "POST", body: JSON.stringify({ resultado: $("#a-res").value, justificativa: $("#a-just").value, prioridade: $("#a-prio").value || null }) });
        abrirCaso(id); carregarFila(); } catch (er) { $("#caso-msg").textContent = er.message; } };
    $("#f-enc").onsubmit = async (e) => { e.preventDefault();
      try { const r = await api(`/manifestacoes/${id}/encaminhamentos`, { method: "POST", body: JSON.stringify({ area: $("#e-area").value, responsavel: $("#e-resp").value }) });
        $("#caso-msg").textContent = `Encaminhado (${r.sistema}); prazo-alvo ${new Date(r.prazo_alvo).toLocaleString("pt-BR")}.`; } catch (er) { $("#caso-msg").textContent = er.message; } };
  } catch (e) { box.textContent = e.message; }
}

// ---------------------------------------------------------------- status
$("#form-status").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = $("#saida-status"); out.hidden = false;
  try {
    const r = await fetch(`${API}/status/${encodeURIComponent($("#s-protocolo").value.trim())}?codigo=${encodeURIComponent($("#s-codigo").value)}`);
    const j = await r.json();
    if (!r.ok) { out.textContent = j.detail === "protocolo e código não conferem" ? "Não encontrei um registro com esse protocolo e código. Confira os números — uma pessoa da equipe também pode ajudar." : j.detail; return; }
    out.innerHTML = `<p>${esc(j.mensagem)}</p><p class="ia">${esc(j.aviso_prazo)}</p><ol>${j.historico.map((h) => `<li>${new Date(h.quando).toLocaleDateString("pt-BR")} — ${esc(h.status)}${h.mensagem ? ": " + esc(h.mensagem) : ""}</li>`).join("")}</ol>`;
    $("#direitos").hidden = false;
  } catch { out.textContent = "Sem conexão. Tente de novo quando a rede voltar."; }
});

// ---------------------------------------------------------------- direitos do titular (LGPD art. 18)
const credencial = () => ({ protocolo: $("#s-protocolo").value.trim(), codigo: $("#s-codigo").value.replace(/\D/g, "") });
async function titular(rota, extra = {}) {
  const r = await fetch(`${API}/titular/${rota}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...credencial(), ...extra }) });
  const j = await r.json();
  if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : "Não foi possível concluir. Confira protocolo e código.");
  return j;
}
function avisoDireitos(t) { const o = $("#saida-direitos"); o.hidden = false; o.textContent = t; }
$("#d-baixar").addEventListener("click", async () => {
  try {
    const dados = await titular("acesso");
    const url = URL.createObjectURL(new Blob([JSON.stringify(dados, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = `meus-dados-${dados.protocolo}.json`; a.click(); URL.revokeObjectURL(url);
    avisoDireitos("Arquivo com todos os seus dados deste protocolo baixado.");
  } catch (e) { avisoDireitos(e.message); }
});
$("#d-corrigir").addEventListener("click", async () => {
  const texto = prompt("O que você quer corrigir ou completar? O texto original continua guardado."); if (!texto) return;
  try { avisoDireitos((await titular("correcao", { texto })).mensagem); } catch (e) { avisoDireitos(e.message); }
});
$("#d-avisos").addEventListener("click", async () => {
  try { avisoDireitos((await titular("consentimento/revogar", { finalidade: "notificacoes" })).mensagem); } catch (e) { avisoDireitos(e.message); }
});
$("#form-pedido").addEventListener("submit", async (e) => {
  e.preventDefault();
  try { avisoDireitos((await titular("pedido", { tipo: $("#d-tipo").value, detalhe: $("#d-detalhe").value || null })).mensagem); $("#d-detalhe").value = ""; }
  catch (er) { avisoDireitos(er.message); }
});

// ---------------------------------------------------------------- painel
$("#carregar-painel").addEventListener("click", async () => {
  const box = $("#painel"); box.textContent = "Carregando…";
  try {
    const p = await api("/indicadores");
    const tabela = (titulo, obj) => `<div class="cartao"><h4>${titulo}</h4><table>${Object.entries(obj).map(([k, v]) => `<tr><td>${esc(k.replaceAll("_", " "))}</td><td>${esc(v)}</td></tr>`).join("") || "<tr><td>—</td></tr>"}</table></div>`;
    box.innerHTML = `<div class="cartao"><h4>Período</h4><p>${p.periodo_dias} dias · total ${esc(p.total_manifestacoes)} · sigilosas ${esc(p.sigilosas_total)}</p>
        <p>Tempo mediano até 1ª ação humana: ${p.tempo_mediano_primeira_acao_humana_h ?? "dados insuficientes"} h</p>
        <p>Críticos fora da janela: ${esc(p.casos_criticos_fora_da_janela)} · Revisões feitas: ${esc(p.revisoes_humanas_realizadas)}</p></div>` +
      tabela("Por tema", p.por_tema) + tabela("Por tipo", p.por_tipo) + tabela("Por território", p.por_territorio) + tabela("Por canal", p.por_canal) + tabela("Por prioridade", p.por_prioridade) +
      `<div class="cartao"><h4>Leitura</h4><p>${esc(p.leitura)}</p>${p.possivel_subnotificacao.map((s) => `<p>${esc(s)}</p>`).join("")}</div>`;
  } catch (e) { box.textContent = e.message; }
});

// ---------------------------------------------------------------- governança
async function carregarChaves() {
  const box = $("#chaves");
  try {
    const c = await api("/admin/chaves");
    const nomes = { agente_total: "Agente (total)", llm: "Modelo de linguagem", triagem_automatica: "Triagem automática", base_conhecimento: "Respostas da base de conhecimento" };
    box.innerHTML = Object.entries(c).map(([m, on]) => `<label class="check"><input type="checkbox" data-mod="${m}" ${on ? "checked" : ""}> ${nomes[m]} — ${on ? "ligado" : "<strong>desligado</strong>"}</label>`).join("");
    box.querySelectorAll("[data-mod]").forEach((cb) => cb.onchange = async () => {
      const motivo = prompt("Motivo (obrigatório, vai para a auditoria):"); if (!motivo) { cb.checked = !cb.checked; return; }
      try { await api("/admin/chaves", { method: "POST", body: JSON.stringify({ modulo: cb.dataset.mod, ativo: cb.checked, motivo }) }); } catch (e) { alert(e.message); }
      carregarChaves();
    });
  } catch (e) { box.textContent = e.message; }
}
$("#verificar-trilha").addEventListener("click", async () => {
  const out = $("#saida-gov"); out.hidden = false;
  try { const r = await api("/admin/auditoria/verificar"); out.textContent = r.integra ? `Trilha íntegra · ${r.total_eventos} eventos.` : `TRILHA COMPROMETIDA no evento ${r.primeiro_seq_invalido}: ${r.motivo}`; }
  catch (e) { out.textContent = e.message; }
});

// ---------------------------------------------------------------- acesso e inicialização
$("#form-config").addEventListener("submit", (e) => { e.preventDefault(); try { localStorage.setItem("escuta.chave", $("#c-chave").value); } catch {} $("#c-chave").value = ""; alert("Chave salva."); novaConversa(); sincronizar(); });

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
(async () => {
  await checarConexao(); await listarLocal();
  if (!chave()) { document.querySelector('[data-aba="config"]').click(); return; }
  retomar(); sincronizar();
})();
