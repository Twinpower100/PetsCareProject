from rest_framework import serializers
from .models import Vacation, SickLeave
from providers.models import Employee

class VacationSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')

    class Meta:
        model = Vacation
        fields = [
            'id', 'employee', 'employee_name', 'provider_location', 'start_date', 'end_date', 
            'vacation_type', 'is_approved', 'approved_by', 'approved_at', 
            'comment', 'created_at', 'updated_at'
        ]
        read_only_fields = ['is_approved', 'approved_by', 'approved_at', 'created_at', 'updated_at']

    def validate(self, data):
        start_date = data.get('start_date') or getattr(self.instance, 'start_date', None)
        end_date = data.get('end_date') or getattr(self.instance, 'end_date', None)
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({"end_date": "End date cannot be earlier than start date"})
        return data

class SickLeaveSerializer(serializers.ModelSerializer):
    employee_name = serializers.ReadOnlyField(source='employee.user.get_full_name')

    class Meta:
        model = SickLeave
        fields = [
            'id', 'employee', 'employee_name', 'provider_location', 'start_date', 'end_date', 
            'sick_leave_type', 'is_confirmed', 'confirmed_by', 'confirmed_at', 
            'comment', 'created_at', 'updated_at'
        ]
        read_only_fields = ['is_confirmed', 'confirmed_by', 'confirmed_at', 'created_at', 'updated_at']

    def validate(self, data):
        start_date = data.get('start_date') or getattr(self.instance, 'start_date', None)
        end_date = data.get('end_date') if 'end_date' in data else getattr(self.instance, 'end_date', None)
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({"end_date": "End date cannot be earlier than start date"})
        return data
