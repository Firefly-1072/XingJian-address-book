const state = { contacts: [], query: "" };

const $ = selector => document.querySelector(selector);
const elements = {
  list: $("#contactList"),
  empty: $("#emptyState"),
  count: $("#countText"),
  search: $("#searchInput"),
  dialog: $("#contactDialog"),
  form: $("#contactForm"),
  title: $("#dialogTitle"),
  id: $("#contactId"),
  name: $("#name"),
  phone: $("#phone"),
  email: $("#email"),
  company: $("#company"),
  notes: $("#notes"),
  error: $("#formError"),
  toast: $("#toast"),
};

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[char]);
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "操作失败，请稍后重试");
  return data;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { elements.toast.hidden = true; }, 2200);
}

async function loadContacts() {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  const data = await api(`/api/contacts?${params}`);
  state.contacts = data.contacts;
  renderContacts(data.total);
}

function renderContacts(total) {
  elements.count.textContent = `${total} 位联系人`;
  elements.empty.hidden = state.contacts.length > 0;
  elements.list.innerHTML = state.contacts.map(contact => `
    <article class="contact-card">
      <div class="avatar">${escapeHtml(contact.name.slice(0, 1).toUpperCase())}</div>
      <div class="contact-main">
        <h2>${escapeHtml(contact.name)}</h2>
        <p class="company">${escapeHtml(contact.company || "未填写公司")}</p>
        <div class="details">
          ${contact.phone ? `<span>☎ ${escapeHtml(contact.phone)}</span>` : ""}
          ${contact.email ? `<span>✉ ${escapeHtml(contact.email)}</span>` : ""}
        </div>
        ${contact.notes ? `<p class="notes">${escapeHtml(contact.notes)}</p>` : ""}
      </div>
      <div class="card-actions">
        <button data-action="edit" data-id="${contact.id}">编辑</button>
        <button data-action="delete" data-id="${contact.id}" class="danger">删除</button>
      </div>
    </article>
  `).join("");
}

function openDialog(contact = null) {
  elements.form.reset();
  elements.error.hidden = true;
  elements.id.value = contact?.id || "";
  elements.name.value = contact?.name || "";
  elements.phone.value = contact?.phone || "";
  elements.email.value = contact?.email || "";
  elements.company.value = contact?.company || "";
  elements.notes.value = contact?.notes || "";
  elements.title.textContent = contact ? "编辑联系人" : "添加联系人";
  elements.dialog.showModal();
  elements.name.focus();
}

function closeDialog() {
  elements.dialog.close();
}

$("#addButton").addEventListener("click", () => openDialog());
$("#closeDialog").addEventListener("click", closeDialog);
$("#cancelButton").addEventListener("click", closeDialog);

elements.dialog.addEventListener("click", event => {
  if (event.target === elements.dialog) closeDialog();
});

elements.form.addEventListener("submit", async event => {
  event.preventDefault();
  const id = elements.id.value;
  const body = {
    name: elements.name.value,
    phone: elements.phone.value,
    email: elements.email.value,
    company: elements.company.value,
    notes: elements.notes.value,
  };
  try {
    await api(id ? `/api/contacts/${id}` : "/api/contacts", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(body),
    });
    closeDialog();
    showToast(id ? "联系人已更新" : "联系人已添加");
    await loadContacts();
  } catch (error) {
    elements.error.textContent = error.message;
    elements.error.hidden = false;
  }
});

elements.list.addEventListener("click", async event => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const contact = state.contacts.find(item => item.id === Number(button.dataset.id));
  if (!contact) return;

  if (button.dataset.action === "edit") openDialog(contact);
  if (button.dataset.action === "delete" && confirm(`确定删除“${contact.name}”吗？`)) {
    try {
      await api(`/api/contacts/${contact.id}`, { method: "DELETE" });
      showToast("联系人已删除");
      await loadContacts();
    } catch (error) {
      showToast(error.message);
    }
  }
});

let searchTimer;
elements.search.addEventListener("input", event => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.query = event.target.value.trim();
    loadContacts().catch(error => showToast(error.message));
  }, 250);
});

loadContacts().catch(error => showToast(error.message));
