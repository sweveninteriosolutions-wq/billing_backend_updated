from fastapi import Depends, HTTPException, status
from app.utils.get_user import get_current_user
from app.models.users.user_models import User


def require_role(roles: list[str]):
    async def role_checker(user: User = Depends(get_current_user)):
        if user.role.lower() not in [r.lower() for r in roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )
        return user
    return role_checker
