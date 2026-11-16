const state = { contacts: [], filter: "all", query: "", editingId: null, deletingId: null };

const $ = (selector) => document.querySelector(selector);
const elements = {
  grid: $("#contactGrid"), empty: $("#emptyState"), emptyText: $("#emptyText"),
  search: $("#searchInput"), allCount: $("#allCount"), favoriteCount: $("#favoriteCount"), visibleCount: $("#visibleCount"),
  title: $("#pageTitle"), subtitle: $("#pageSubtitle"), dialog: $("#contactDialog"), form: $("#contactForm"),
  dialogTitle: $("#dialogTitle"), name: $("#nameInput"), company: $("#companyInput"), favorite: $("#favoriteInput"),
  notes: $("#notesInput"), methods: $("#methodsList"), methodTemplate: $("#methodTemplate"),
  importInput: $("#importInput"), confirmDialog: $("#confirmDialog"), toast: $("#toast"),
  authScreen: $("#authScreen"), appShell: $("#appShell"), authMessage: $("#authMessage"),
  accountName: $("#accountName"), accountPhone: $("#accountPhone"), accountAvatar: $("#accountAvatar")
};

const methodIcons = { phone: "☎", email: "@", social: "#", address: "⌖", other: "·" };
const methodNames = { phone: "电话", email: "邮箱", social: "社交账号", address: "地址", other: "其他" };

function escapeHtml(value = "") {
  const node = document.createElement("span");
  node.textContent = String(value);
  return node.innerHTML;
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = "操作失败，请稍后重试";
    try { message = (await response.json()).error || message; } catch (_) { /* response is not JSON */ }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function showToast(message, isError = false) {
  elements.toast.textContent = message;
  elements.toast.className = `toast show${isError ? " error" : ""}`;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => elements.toast.className = "toast", 2600);
}

function debounce(callback, wait = 250) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), wait); };
}

const authCopy = {
  login: ["SIGN IN", "欢迎回来", "登录后进入你的私人通讯录。"],
  register: ["CREATE ACCOUNT", "创建本地账户", "首次使用需要手机号验证。"],
  reset: ["RECOVER ACCESS", "重置密码", "使用注册手机号验证身份。"]
};

function setAuthMessage(message = "", type = "") {
  elements.authMessage.textContent = message;
  elements.authMessage.className = `auth-message${type ? ` ${type}` : ""}`;
}

function switchAuthView(view) {
  document.querySelectorAll(".auth-tab").forEach(tab => {
    const active = tab.dataset.authView === view;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".auth-form").forEach(form => { form.hidden = form.dataset.view !== view; });
  $("#authEyebrow").textContent = authCopy[view][0];
  $("#authTitle").textContent = authCopy[view][1];
  $("#authSubtitle").textContent = authCopy[view][2];
  setAuthMessage();
}

function showAuthenticatedApp(user) {
  elements.authScreen.hidden = true;
  elements.appShell.hidden = false;
  elements.accountName.textContent = user.username;
  elements.accountPhone.textContent = user.phone.replace(/^(\d{3})\d{4}(\d{4})$/, "$1****$2");
  elements.accountAvatar.textContent = user.username.slice(0, 1).toUpperCase();
  loadContacts();
}

async function bootstrapAuth() {
  try {
    const status = await api("/api/auth/status");
    if (status.loggedIn) showAuthenticatedApp(status.user);
    else {
      elements.authScreen.hidden = false;
      elements.appShell.hidden = true;
      switchAuthView(status.hasAccounts ? "login" : "register");
      if (!status.hasAccounts) setAuthMessage("检测到这是首次使用，请先注册第一个账户。", "demo");
    }
  } catch (error) { setAuthMessage(error.message, "error"); }
}

async function sendCode(purpose, button) {
  const phone = $(purpose === "register" ? "#registerPhone" : "#resetPhone").value.trim();
  button.disabled = true;
  try {
    const result = await api("/api/auth/send-code", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone, purpose })
    });
    setAuthMessage(`本地演示验证码：${result.demoCode}（10分钟内有效）`, "demo");
    const codeInput = $(purpose === "register" ? "#registerCode" : "#resetCode");
    codeInput.value = result.demoCode;
    codeInput.focus();
    let remaining = 60;
    button.textContent = `${remaining}秒后重试`;
    const timer = setInterval(() => {
      remaining -= 1;
      button.textContent = `${remaining}秒后重试`;
      if (remaining <= 0) { clearInterval(timer); button.disabled = false; button.textContent = "重新获取"; }
    }, 1000);
  } catch (error) { button.disabled = false; setAuthMessage(error.message, "error"); }
}

async function submitLogin(event) {
  event.preventDefault();
  try {
    const result = await api("/api/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account: $("#loginAccount").value.trim(), password: $("#loginPassword").value })
    });
    showAuthenticatedApp(result.user);
    showToast("登录成功");
  } catch (error) { setAuthMessage(error.message, "error"); }
}

async function submitRegister(event) {
  event.preventDefault();
  try {
    const result = await api("/api/auth/register", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: $("#registerUsername").value.trim(), phone: $("#registerPhone").value.trim(),
        code: $("#registerCode").value.trim(), password: $("#registerPassword").value
      })
    });
    showAuthenticatedApp(result.user);
    showToast("注册成功，欢迎使用星笺");
  } catch (error) { setAuthMessage(error.message, "error"); }
}

async function submitReset(event) {
  event.preventDefault();
  try {
    const result = await api("/api/auth/reset-password", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone: $("#resetPhone").value.trim(), code: $("#resetCode").value.trim(), password: $("#resetPassword").value })
    });
    switchAuthView("login");
    setAuthMessage(result.message);
  } catch (error) { setAuthMessage(error.message, "error"); }
}

async function logout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (_) { /* local logout still clears UI */ }
  state.contacts = [];
  elements.appShell.hidden = true;
  elements.authScreen.hidden = false;
  $("#loginPassword").value = "";
  switchAuthView("login");
  setAuthMessage("已安全退出");
}

async function loadContacts() {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.filter === "favorite") params.set("favorite", "1");
  try {
    const data = await api(`/api/contacts?${params}`);
    state.contacts = data.contacts;
    elements.allCount.textContent = data.total;
    elements.favoriteCount.textContent = data.favoriteCount;
    renderContacts();
  } catch (error) { showToast(error.message, true); }
}

function renderContacts() {
  elements.visibleCount.textContent = state.contacts.length;
  elements.grid.innerHTML = state.contacts.map((contact, index) => {
    const methods = contact.methods.slice(0, 2).map(method => `
      <div class="method-line"><i>${methodIcons[method.type] || "·"}</i><span title="${escapeHtml(method.value)}">${method.label ? `${escapeHtml(method.label)} · ` : ""}${escapeHtml(method.value)}</span></div>
    `).join("");
    const remainder = contact.methods.length > 2 ? `另有 ${contact.methods.length - 2} 项` : `${contact.methods.length} 项联系方式`;
    return `
      <article class="contact-card${contact.isFavorite ? " favorite" : ""}" style="animation-delay:${Math.min(index * 35, 280)}ms">
        <div class="card-head">
          <div class="avatar">${escapeHtml(contact.name.slice(0, 1).toUpperCase())}</div>
          <div class="card-identity"><h2>${escapeHtml(contact.name)}</h2><p>${escapeHtml(contact.company || "未填写公司或组织")}</p></div>
          <button class="favorite-button${contact.isFavorite ? " active" : ""}" data-action="favorite" data-id="${contact.id}" aria-label="${contact.isFavorite ? "取消收藏" : "添加收藏"}">★</button>
        </div>
        <div class="method-preview">${methods || '<span class="no-method">暂未添加联系方式</span>'}</div>
        <div class="card-footer"><span class="method-count">${remainder}</span><div class="card-menu"><button data-action="edit" data-id="${contact.id}">编辑</button><button class="delete" data-action="delete" data-id="${contact.id}">删除</button></div></div>
      </article>`;
  }).join("");
  const isEmpty = state.contacts.length === 0;
  elements.grid.hidden = isEmpty;
  elements.empty.hidden = !isEmpty;
  elements.emptyText.textContent = state.query ? "没有找到匹配的联系人，试试其他关键词。" : state.filter === "favorite" ? "收藏重要联系人后，可以在这里快速找到他们。" : "添加第一位联系人，建立你们之间的连接。";
}

function addMethod(method = {}) {
  const fragment = elements.methodTemplate.content.cloneNode(true);
  const row = fragment.querySelector(".method-row");
  row.querySelector(".method-type").value = method.type || "phone";
  row.querySelector(".method-label").value = method.label || "";
  row.querySelector(".method-value").value = method.value || "";
  row.querySelector(".remove-method").addEventListener("click", () => {
    row.remove();
    if (!elements.methods.children.length) addMethod();
  });
  elements.methods.appendChild(fragment);
}

function openContactDialog(contact = null) {
  state.editingId = contact?.id || null;
  elements.dialogTitle.textContent = contact ? "编辑联系人" : "新建联系人";
  elements.name.value = contact?.name || "";
  elements.company.value = contact?.company || "";
  elements.favorite.checked = contact?.isFavorite || false;
  elements.notes.value = contact?.notes || "";
  elements.methods.innerHTML = "";
  (contact?.methods?.length ? contact.methods : [{}]).forEach(addMethod);
  elements.dialog.showModal();
  setTimeout(() => elements.name.focus(), 50);
}

function closeContactDialog() { elements.dialog.close(); state.editingId = null; }

async function saveContact(event) {
  event.preventDefault();
  if (!elements.form.reportValidity()) return;
  const methods = [...elements.methods.querySelectorAll(".method-row")].map(row => ({
    type: row.querySelector(".method-type").value,
    label: row.querySelector(".method-label").value.trim(),
    value: row.querySelector(".method-value").value.trim()
  })).filter(method => method.value);
  const payload = { name: elements.name.value.trim(), company: elements.company.value.trim(), isFavorite: elements.favorite.checked, notes: elements.notes.value.trim(), methods };
  const isEditing = Boolean(state.editingId);
  try {
    await api(isEditing ? `/api/contacts/${state.editingId}` : "/api/contacts", {
      method: isEditing ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    closeContactDialog();
    await loadContacts();
    showToast(isEditing ? "联系人已更新" : "联系人已添加");
  } catch (error) { showToast(error.message, true); }
}

async function handleGridClick(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = Number(button.dataset.id);
  const contact = state.contacts.find(item => item.id === id);
  if (!contact) return;
  if (button.dataset.action === "edit") openContactDialog(contact);
  if (button.dataset.action === "delete") { state.deletingId = id; elements.confirmDialog.showModal(); }
  if (button.dataset.action === "favorite") {
    try {
      await api(`/api/contacts/${id}/favorite`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ isFavorite: !contact.isFavorite }) });
      await loadContacts();
      showToast(contact.isFavorite ? "已取消收藏" : "已加入收藏");
    } catch (error) { showToast(error.message, true); }
  }
}

async function confirmDelete() {
  try {
    await api(`/api/contacts/${state.deletingId}`, { method: "DELETE" });
    elements.confirmDialog.close();
    state.deletingId = null;
    await loadContacts();
    showToast("联系人已删除");
  } catch (error) { showToast(error.message, true); }
}

async function importExcel(event) {
  const file = event.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const result = await api("/api/import", { method: "POST", body: formData });
    await loadContacts();
    showToast(result.message);
  } catch (error) { showToast(error.message, true); }
  finally { elements.importInput.value = ""; }
}

document.querySelectorAll(".nav-item").forEach(button => button.addEventListener("click", () => {
  document.querySelectorAll(".nav-item").forEach(item => item.classList.toggle("active", item === button));
  state.filter = button.dataset.filter;
  elements.title.textContent = state.filter === "favorite" ? "我的收藏" : "全部联系人";
  elements.subtitle.textContent = state.filter === "favorite" ? "重要的人，始终触手可及" : "集中管理重要的人与每一种联系方式";
  loadContacts();
}));
elements.search.addEventListener("input", debounce(event => { state.query = event.target.value.trim(); loadContacts(); }));
document.addEventListener("keydown", event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); elements.search.focus(); } });
$("#addButton").addEventListener("click", () => openContactDialog());
$("#emptyAddButton").addEventListener("click", () => openContactDialog());
$("#addMethodButton").addEventListener("click", () => addMethod());
$("#closeDialogButton").addEventListener("click", closeContactDialog);
$("#cancelButton").addEventListener("click", closeContactDialog);
elements.form.addEventListener("submit", saveContact);
elements.grid.addEventListener("click", handleGridClick);
$("#importButton").addEventListener("click", () => elements.importInput.click());
elements.importInput.addEventListener("change", importExcel);
$("#cancelDeleteButton").addEventListener("click", () => { elements.confirmDialog.close(); state.deletingId = null; });
$("#confirmDeleteButton").addEventListener("click", confirmDelete);
elements.dialog.addEventListener("click", event => { if (event.target === elements.dialog) closeContactDialog(); });
elements.confirmDialog.addEventListener("click", event => { if (event.target === elements.confirmDialog) elements.confirmDialog.close(); });

document.querySelectorAll(".auth-tab").forEach(tab => tab.addEventListener("click", () => switchAuthView(tab.dataset.authView)));
document.querySelectorAll("[data-switch-view]").forEach(button => button.addEventListener("click", () => switchAuthView(button.dataset.switchView)));
document.querySelectorAll("[data-send-code]").forEach(button => button.addEventListener("click", () => sendCode(button.dataset.sendCode, button)));
$("#loginForm").addEventListener("submit", submitLogin);
$("#registerForm").addEventListener("submit", submitRegister);
$("#resetForm").addEventListener("submit", submitReset);
$("#logoutButton").addEventListener("click", logout);

bootstrapAuth();
