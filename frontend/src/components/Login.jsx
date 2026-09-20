import React, { useState } from 'react';
import { useAuthStore } from '../store/authStore';
import api from '../store/api';
import { KeyRound, ShieldCheck, User } from 'lucide-react';

export default function Login() {
  const setToken = useAuthStore((state) => state.setToken);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleLogin = async (role) => {
    setIsLoading(true);
    setError(null);
    try {
      // For this phase, the SSO endpoint seeds an admin and a user based on the mock backend
      const res = await api.get(`/auth/sso/microsoft?role=${role}`);
      setToken(res.data.access_token);
    } catch (err) {
      setError("Authentication failed. Ensure the backend is running.");
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
            <div className="w-12 h-12 bg-indigo-600 rounded-xl flex items-center justify-center shadow-lg">
                <span className="text-white font-bold text-xl">AOS</span>
            </div>
        </div>
        <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
          Sign in to AgentOS
        </h2>
        <p className="mt-2 text-center text-sm text-gray-600">
          Enterprise AI Workflow Orchestrator
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10 border border-gray-200">

          {error && (
              <div className="mb-4 bg-red-50 text-red-600 p-3 rounded-md text-sm border border-red-100">
                  {error}
              </div>
          )}

          <div className="space-y-6">
            <div>
              <button
                onClick={() => handleLogin('admin')}
                disabled={isLoading}
                className="w-full flex justify-center items-center gap-2 py-3 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-[#2F2F2F] hover:bg-black focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-900 transition-colors disabled:opacity-50"
              >
                <ShieldCheck className="w-4 h-4" />
                Enterprise Sign-In (Microsoft SSO)
              </button>
            </div>

            <div className="mt-6">
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-300" />
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-2 bg-white text-gray-500">Developer Testing</span>
                </div>
              </div>

              <div className="mt-6 grid grid-cols-2 gap-3">
                <button
                  onClick={() => handleLogin('admin')}
                  disabled={isLoading}
                  className="w-full flex justify-center items-center gap-2 py-2 px-4 border border-gray-300 rounded-md shadow-sm bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
                >
                  <KeyRound className="w-4 h-4 text-indigo-600" />
                  Admin
                </button>
                <button
                  onClick={() => handleLogin('user')}
                  disabled={isLoading}
                  className="w-full flex justify-center items-center gap-2 py-2 px-4 border border-gray-300 rounded-md shadow-sm bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
                >
                  <User className="w-4 h-4 text-gray-500" />
                  User
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
