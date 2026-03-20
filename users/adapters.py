from django.shortcuts import redirect
from django.urls import reverse
 
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.exceptions import ImmediateHttpResponse
 
from users.models import User
 
 
class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):

    def pre_social_login(self, request, sociallogin):

        email = sociallogin.account.extra_data.get("email", "").lower().strip()
 
        if not email:
            # No email in the Google payload — reject immediately.
            raise ImmediateHttpResponse(
                redirect(reverse("login_page") + "?error=no_account")
            )
 
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Email is not registered — reject and send back to login page.
            raise ImmediateHttpResponse(
                redirect(reverse("session_login_page") + "?error=no_account")
            )
 
        # Email matches an existing user, then attach the social account to that user
        # allauth can then complete the session login without trying to create a new user
        sociallogin.connect(request, user)