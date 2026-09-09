from app.models.membership import MembershipRole

ROLE_PERMISSIONS = {
    MembershipRole.owner: {
        "task.create", "task.create_confidential", "task.update", "task.delete",
        "member.invite", "member.remove", "member.update_role",
        "organization.update", "organization.delete",
    },
    MembershipRole.admin: {
        "task.create", "task.create_confidential", "task.update", "task.delete",
        "member.invite", "member.remove",
    },
    MembershipRole.member: {
        "task.create", "task.update",
    },
}


def has_permission(role: MembershipRole, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())
