from django import forms
from .models import Property, Profile


class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = ['title', 'description', 'price', 'location', 'status', 'image']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

        
class ProfileForm(forms.ModelForm):
    phone_number = forms.CharField(required=False)  # <- This is from CustomUser

    class Meta:
        model = Profile
        fields = ['role', 'bio', 'profile_picture', 'company_name', 'aadhaar_number', 'pan_number', 'aadhaar_document', 'pan_document']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields['phone_number'].initial = self.instance.user.phone_number

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.phone_number = self.cleaned_data['phone_number']
        if commit:
            user.save()
            profile.save()
        return profile