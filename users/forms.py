from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()

class UserSignupForm(forms.ModelForm):
    role = forms.ChoiceField(
        choices=[choice for choice in User.USER_ROLES if choice[0] != 'admin'],
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input'}))
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'class': 'form-input'})
    ) 
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number', 'dob']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-input'}),
            'dob': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'})
        }
    
    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user
