# 🚍 IFRN Bus System API

API desenvolvida com **Django + Django REST Framework** para gerenciamento do transporte escolar do IFRN - Campus Apodi.

O sistema substitui listas informais (como grupos de WhatsApp), permitindo que alunos se inscrevam em ônibus e que motoristas/admins gerenciem listas diárias de passageiros.

---

# 📌 Objetivo

Organizar o transporte escolar de forma digital, permitindo:

- Cadastro de ônibus
- Definição de rotas com horários fixos
- Criação de listas diárias de embarque
- Inscrição de alunos nas listas
- Controle por tipo de usuário (aluno, motorista, admin)

---

# 🧱 Arquitetura do sistema

O sistema é baseado em 4 entidades principais:

- **Bus** → ônibus físico
- **BusRoute** → horários fixos do ônibus
- **BusList** → lista de passageiros por dia
- **BusListEntry** → aluno inscrito na lista

---

# 👥 Tipos de usuário

- **Aluno** → entra e sai de listas
- **Motorista** → visualiza listas e passageiros
- **Administrador** → gerencia ônibus e rotas

# ⚙️ Tecnologias utilizadas

- Python
- Django
- Django REST Framework
- PostgreSQL (recomendado)

---

# 🚀 Status do projeto

MVP em desenvolvimento

