from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth.models import User
from django.db import transaction
from .models import BankAccount, Transaction
from drf_spectacular.utils import extend_schema
from .serializers import (
    UserSerializer, BankAccountSerializer, TransactionSerializer,
    DepositSerializer, WithdrawSerializer, TransferSerializer
)

@extend_schema(tags=['Authentication'], description='Register a new user and create a bank account')
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        user = serializer.save()
        BankAccount.objects.create(user=user) # type: ignore

@extend_schema(tags=['Account'], description='Get current user bank account details')
class AccountDetailView(generics.RetrieveAPIView):
    serializer_class = BankAccountSerializer
    permissions_classes = [IsAuthenticated]

    # We override this to return the current user's bank account
    def get_object(self):
        return self.request.user.bank_account

@extend_schema(tags=['Transactions'], request=DepositSerializer, description='Deposit money into your account')
class DepositView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data['amount'] # type: ignore
        account = request.user.bank_account

        account.balance += amount
        account.save()

        Transaction.objects.create( # type: ignore
            account=account,
            transaction_type='DEPOSIT',
            amount=amount,
            description='Deposit to account'
        )

        return Response({
            'message': 'Deposit successful',
            'new_balance': str(account.balance)
        })

@extend_schema(tags=['Transactions'], request=WithdrawSerializer, description='Withdraw money from your account')
class WithdrawView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data['amount'] # type: ignore
        account = request.user.bank_account

        if account.balance < amount:
            return Response(
                {'error': 'Insuficient funds'},
                status=status.HTTP_400_BAD_REQUEST
            )

        account.balance -= amount
        account.save()

        Transaction.objects.create( # type: ignore
            account=account,
            transaction_type='WITHDRAWAL',
            amount=amount,
            description='Withdrawal from account'
        )

        return Response({
            'message': 'Withdrawal successful',
            'new_balance': str(account.balance)
        })

@extend_schema(tags=['Transactions'], request=TransferSerializer, description='Transfer money to another user')
class TransferView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data['amount'] # type: ignore
        recipient_username = serializer.validated_data['recipient_username'] # type: ignore

        sender_account = request.user.bank_account

        if sender_account.user.username == recipient_username:
            return Response(
                {'error': 'Cannot transfer to yourself'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            recipient = User.objects.get(username=recipient_username)
        except User.DoesNotExist: # type: ignore
            return Response(
                {'error': 'Recipient not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if sender_account.balance < amount:
            return Response(
                {'error': 'Insufficient funds'},
                status=status.HTTP_400_BAD_REQUEST
            )

        recipient_account = recipient.bank_account

        with transaction.atomic(): # type: ignore
            sender_account.balance -= amount
            sender_account.save()

            recipient_account.balance += amount
            recipient_account.save()

            Transaction.objects.create( # type: ignore
                account=sender_account,
                transaction_type='TRANSFER_OUT',
                amount=amount,
                description=f'Transfer to {recipient_username}'
            )

            Transaction.objects.create( # type: ignore
                account=recipient_account,
                transaction_type='TRANSFER_IN',
                amount=amount,
                description=f'Transfer from {request.user.username}'
            )

        return Response({
            'message': 'Transfer successful',
            'new_balance': str(sender_account.balance)
        })

@extend_schema(tags=['Transactions'], description='View your transaction history')
class TransactionHistoryView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter( # type: ignore
            account=self.request.user.bank_account
        ).order_by('-created_at')
